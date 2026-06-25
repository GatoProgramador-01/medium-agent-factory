# FILE: infra/bootstrap/main.tf
#
# Run this ONCE before any other Terraform in this repo.
# It creates the S3 bucket + DynamoDB table used as remote state backend
# for both app-runner/ and ecs/ environments.
#
# Usage:
#   cd infra/bootstrap
#   terraform init       # local state is fine here — bootstrap is run once
#   terraform apply
#   # Copy the backend block from outputs into app-runner/backend.tf / ecs/backend.tf

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# ── Resolve caller identity (account ID used in bucket name for global uniqueness) ──
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  # Bucket names must be globally unique — embed account ID to guarantee that
  bucket_name = "${var.project_name}-${var.environment}-terraform-state-${local.account_id}"
  table_name  = "${var.project_name}-${var.environment}-terraform-locks"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── S3 bucket: remote state storage ─────────────────────────────────────────────
resource "aws_s3_bucket" "state" {
  bucket = local.bucket_name

  tags = merge(local.common_tags, {
    Name = local.bucket_name
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access — state files must never be public
resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Prevent accidental deletion of the bucket (state files inside are version-protected)
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    # Keep noncurrent versions for 90 days — long enough to roll back any apply
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# ── DynamoDB table: state locking ────────────────────────────────────────────────
resource "aws_dynamodb_table" "locks" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST" # on-demand — lock table traffic is negligible
  hash_key     = "LockID"          # Terraform expects exactly this attribute name

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(local.common_tags, {
    Name = local.table_name
  })

  lifecycle {
    prevent_destroy = true
  }
}
