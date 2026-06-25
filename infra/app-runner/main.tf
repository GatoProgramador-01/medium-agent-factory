# FILE: infra/app-runner/main.tf
#
# Option A — AWS App Runner (~$15-20/month at min capacity)
#
# App Runner manages the container runtime, load balancing, TLS, and scaling
# automatically. No VPC, ALB, or ECS cluster to maintain.
# Trade-off: less control over networking; suitable for portfolio/light-traffic APIs.
#
# Prerequisites:
#   1. Run infra/bootstrap first to create S3 + DynamoDB state backend.
#   2. Store secrets in SSM Parameter Store (see infra/README.md).
#   3. Set var.image_uri to a reachable container image.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment after running bootstrap and replace placeholder values:
  # backend "s3" {
  #   bucket         = "medium-agent-factory-prod-terraform-state-<ACCOUNT_ID>"
  #   key            = "medium-agent-factory/app-runner/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "medium-agent-factory-prod-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── SSM parameters (read-only — values are set manually outside Terraform) ──────
# We only reference these so we can pass their ARNs to App Runner.
# The actual secret values are NEVER in Terraform state.
data "aws_ssm_parameter" "mongodb_uri" {
  name            = var.mongodb_ssm_path
  with_decryption = false # App Runner reads the decrypted value at runtime via IAM
}

data "aws_ssm_parameter" "anthropic_api_key" {
  name            = var.anthropic_api_key_ssm_path
  with_decryption = false
}

data "aws_ssm_parameter" "tavily_api_key" {
  name            = var.tavily_api_key_ssm_path
  with_decryption = false
}

data "aws_ssm_parameter" "langchain_api_key" {
  name            = var.langchain_api_key_ssm_path
  with_decryption = false
}

# ── IAM role: App Runner instance role ──────────────────────────────────────────
# This role is assumed by the running container — it grants access to SSM.
resource "aws_iam_role" "app_runner_instance" {
  name = "${local.name_prefix}-app-runner-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "tasks.apprunner.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "app_runner_ssm" {
  name = "${local.name_prefix}-ssm-read"
  role = aws_iam_role.app_runner_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadSecrets"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        # Least privilege: only the four parameters this service needs
        Resource = [
          data.aws_ssm_parameter.mongodb_uri.arn,
          data.aws_ssm_parameter.anthropic_api_key.arn,
          data.aws_ssm_parameter.tavily_api_key.arn,
          data.aws_ssm_parameter.langchain_api_key.arn,
        ]
      },
      {
        Sid      = "DecryptSSMKMS"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*" # KMS key ARN unknown at write time; tighten in prod with specific key ARN
      }
    ]
  })
}

# ── IAM role: App Runner access role (ECR pull) ─────────────────────────────────
# Separate from the instance role — this is used by App Runner's control plane
# to pull the image from ECR before the container starts.
# Not needed if pulling from a public registry (GHCR public, Docker Hub).
resource "aws_iam_role" "app_runner_access" {
  name = "${local.name_prefix}-app-runner-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "build.apprunner.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

# AWS-managed policy that grants the minimum ECR pull permissions App Runner needs
resource "aws_iam_role_policy_attachment" "app_runner_ecr" {
  role       = aws_iam_role.app_runner_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# ── Auto-scaling configuration ───────────────────────────────────────────────────
resource "aws_apprunner_auto_scaling_configuration_version" "this" {
  auto_scaling_configuration_name = "${local.name_prefix}-asc"

  min_size            = var.min_size
  max_size            = var.max_size
  # Scale out when concurrent requests per instance exceed 25
  # (App Runner default is 100 — lower value keeps latency tighter for an API)
  max_concurrency     = 25

  tags = local.common_tags
}

# ── App Runner service ───────────────────────────────────────────────────────────
resource "aws_apprunner_service" "backend" {
  service_name = "${local.name_prefix}-backend"

  source_configuration {
    # Set authentication_configuration only when pulling from a private ECR repo.
    # Remove this block entirely if using a public image (GHCR public, Docker Hub).
    authentication_configuration {
      access_role_arn = aws_iam_role.app_runner_access.arn
    }

    image_repository {
      image_identifier      = var.image_uri
      image_repository_type = "ECR" # Change to "ECR_PUBLIC" or omit auth block for public registries

      image_configuration {
        port = "8000"

        # App Runner reads SSM SecureString values and injects them as env vars.
        # The container sees plaintext — no SDK calls needed inside the app.
        runtime_environment_secrets = {
          MONGODB_URI       = data.aws_ssm_parameter.mongodb_uri.arn
          ANTHROPIC_API_KEY = data.aws_ssm_parameter.anthropic_api_key.arn
          TAVILY_API_KEY    = data.aws_ssm_parameter.tavily_api_key.arn
          LANGCHAIN_API_KEY = data.aws_ssm_parameter.langchain_api_key.arn
        }

        runtime_environment_variables = {
          # Non-secret configuration injected at the Terraform level
          APP_ENV = var.environment
        }
      }
    }

    # Disable auto-deploy on ECR push — deploy only on explicit terraform apply
    # Change to true if you want CD directly from ECR tag pushes
    auto_deployments_enabled = false
  }

  instance_configuration {
    # 1 vCPU / 2 GB — smallest tier that comfortably handles uvicorn + LangChain
    # App Runner CPU unit: "1 vCPU" | "2 vCPU" | "4 vCPU"
    cpu    = "1 vCPU"
    memory = "2 GB"

    # The instance role grants the container access to SSM and any future AWS services
    instance_role_arn = aws_iam_role.app_runner_instance.arn
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10 # seconds between checks — low enough to detect fast restarts
    timeout             = 5
    healthy_threshold   = 1 # single success marks instance healthy (fast startup)
    unhealthy_threshold = 3 # 3 consecutive failures before replacement
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.this.arn

  tags = local.common_tags
}
