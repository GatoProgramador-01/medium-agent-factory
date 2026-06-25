# FILE: infra/ecs/main.tf
#
# Option B — ECS Fargate + ALB (~$25-40/month)
#
# More operational control than App Runner: explicit VPC, security groups,
# ALB routing rules, CloudWatch log groups, and deployment circuit breaker.
# Preferred for production when you need private networking, WAF, or custom
# routing. Overkill for a low-traffic portfolio API but demonstrates production-
# grade patterns.
#
# Prerequisites:
#   1. Run infra/bootstrap to create S3 + DynamoDB state backend.
#   2. Push the backend Docker image to ECR (see infra/README.md).
#   3. Store secrets in SSM Parameter Store (see infra/README.md).

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
  #   key            = "medium-agent-factory/ecs/terraform.tfstate"
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
  image_uri   = "${var.ecr_repository_url}:${var.image_tag}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── SSM parameters (reference only — values managed outside Terraform) ───────────
data "aws_ssm_parameter" "mongodb_uri" {
  name            = var.mongodb_ssm_path
  with_decryption = false
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

# ════════════════════════════════════════════════════════════════════════════════
# VPC — two public subnets across two AZs
# Simplified: no private subnets to reduce NAT Gateway cost (~$32/month).
# The ECS task and ALB both sit in public subnets; traffic from ECS→internet
# goes directly via the internet gateway. Add private subnets + NAT Gateway
# if tasks must be isolated from inbound internet traffic.
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true # Required for ECR VPC endpoints (if added later)

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

# Two public subnets — ALB requires at least two AZs
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.region}a"
  map_public_ip_on_launch = true # Tasks need outbound internet (ECR pull, LLM APIs)

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-a"
  })
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.region}b"
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-b"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# ════════════════════════════════════════════════════════════════════════════════
# Security groups
# ════════════════════════════════════════════════════════════════════════════════

# ALB: accept HTTP from the internet; forward to ECS tasks on port 8000
resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Allow inbound HTTP to the ALB from the internet."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS — uncomment when a certificate is attached to the ALB listener
  # ingress {
  #   description = "HTTPS from anywhere"
  #   from_port   = 443
  #   to_port     = 443
  #   protocol    = "tcp"
  #   cidr_blocks = ["0.0.0.0/0"]
  # }

  egress {
    description = "Allow all outbound (forward to ECS tasks)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb-sg"
  })
}

# ECS tasks: only accept traffic from the ALB security group
resource "aws_security_group" "ecs_tasks" {
  name        = "${local.name_prefix}-ecs-tasks-sg"
  description = "Allow inbound on port 8000 from ALB only; allow all outbound."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "FastAPI from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow all outbound (ECR pull, MongoDB Atlas, LLM APIs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-tasks-sg"
  })
}

# ════════════════════════════════════════════════════════════════════════════════
# Application Load Balancer
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  # Keep access logs disabled for portfolio — enable in prod and point to an S3 bucket
  enable_deletion_protection = false

  tags = local.common_tags
}

resource "aws_lb_target_group" "backend" {
  name        = "${local.name_prefix}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Fargate tasks register by IP, not instance ID

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = local.common_tags
}

# HTTP listener — forwards all traffic to the ECS target group
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ════════════════════════════════════════════════════════════════════════════════
# CloudWatch log group
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.name_prefix}-backend"
  retention_in_days = 30 # 30 days balances debuggability vs cost

  tags = local.common_tags
}

# ════════════════════════════════════════════════════════════════════════════════
# IAM — task execution role (ECS control plane: ECR pull + CloudWatch logs)
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_iam_role" "ecs_task_execution" {
  name = "${local.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

# AWS-managed policy covers ECR pull + CloudWatch Logs write
resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy: allow the execution role to fetch SecureString SSM params
# (needed so ECS can inject secrets into container env at task start)
resource "aws_iam_role_policy" "ecs_task_execution_ssm" {
  name = "${local.name_prefix}-ssm-secrets"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadSSMSecrets"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
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
        Resource = "*" # Tighten to specific KMS key ARN in production
      }
    ]
  })
}

# ── Task role (permissions the running application code needs) ───────────────────
# Separate from execution role — follows least-privilege: the app currently
# needs no AWS APIs, so this role has no policies attached. Add policies here
# if the app later needs S3, Bedrock, SQS, etc.
resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

# ════════════════════════════════════════════════════════════════════════════════
# ECS Cluster
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled" # Enhanced CloudWatch metrics (CPU, memory, network per task)
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ════════════════════════════════════════════════════════════════════════════════
# ECS Task Definition
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  network_mode             = "awsvpc" # Required for Fargate
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu    # 512 = 0.5 vCPU
  memory                   = var.task_memory # 1024 = 1 GB

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = local.image_uri
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      # Secrets injected from SSM at task start — visible as env vars inside the container
      secrets = [
        {
          name      = "MONGODB_URI"
          valueFrom = data.aws_ssm_parameter.mongodb_uri.arn
        },
        {
          name      = "ANTHROPIC_API_KEY"
          valueFrom = data.aws_ssm_parameter.anthropic_api_key.arn
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = data.aws_ssm_parameter.tavily_api_key.arn
        },
        {
          name      = "LANGCHAIN_API_KEY"
          valueFrom = data.aws_ssm_parameter.langchain_api_key.arn
        }
      ]

      environment = [
        {
          name  = "APP_ENV"
          value = var.environment
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "backend"
        }
      }

      # Give the uvicorn server time to shut down gracefully before SIGKILL
      stopTimeout = 30
    }
  ])

  tags = local.common_tags
}

# ════════════════════════════════════════════════════════════════════════════════
# ECS Service
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # Disable ECS-managed tags to avoid circular dependency on task role tag propagation
  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true # Required in public subnets without NAT Gateway
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true  # Automatic rollback if new tasks fail to reach steady state
    rollback = true
  }

  deployment_controller {
    type = "ECS" # Use CODE_DEPLOY for blue/green when traffic shifting is needed
  }

  # Ignore task definition changes triggered outside Terraform (e.g. CI/CD pipeline
  # that updates the image tag). Terraform still manages the service config.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.ecs_task_execution_managed,
  ]

  tags = local.common_tags
}

# ════════════════════════════════════════════════════════════════════════════════
# CloudWatch Alarms (basic — expand in production)
# ════════════════════════════════════════════════════════════════════════════════

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${local.name_prefix}-ecs-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80 # Alert at 80% CPU — time to scale or right-size the task

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }

  alarm_description = "ECS service CPU exceeds 80% — consider scaling or upgrading task CPU."
  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  alarm_name          = "${local.name_prefix}-ecs-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }

  alarm_description = "ECS service memory exceeds 85% — uvicorn workers may OOM."
  treat_missing_data = "notBreaching"

  tags = local.common_tags
}
