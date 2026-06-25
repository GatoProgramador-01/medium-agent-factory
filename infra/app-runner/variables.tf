# FILE: infra/app-runner/variables.tf

variable "project_name" {
  type        = string
  description = "Project identifier — used as the first segment in all resource names."
  default     = "medium-agent-factory"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev | staging | prod)."
  default     = "prod"
}

variable "region" {
  type        = string
  description = "AWS region for the App Runner service."
  default     = "us-east-1"
}

variable "image_uri" {
  type        = string
  description = <<-EOD
    Full container image URI including tag.
    Examples:
      ECR:  123456789012.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory:latest
      GHCR: ghcr.io/<owner>/medium-agent-factory-backend:latest
  EOD
}

variable "mongodb_ssm_path" {
  type        = string
  description = "SSM Parameter Store path for MONGODB_URI (SecureString)."
  default     = "/medium-agent-factory/prod/MONGODB_URI"
}

variable "anthropic_api_key_ssm_path" {
  type        = string
  description = "SSM Parameter Store path for ANTHROPIC_API_KEY (SecureString)."
  default     = "/medium-agent-factory/prod/ANTHROPIC_API_KEY"
}

variable "tavily_api_key_ssm_path" {
  type        = string
  description = "SSM Parameter Store path for TAVILY_API_KEY (SecureString)."
  default     = "/medium-agent-factory/prod/TAVILY_API_KEY"
}

variable "langchain_api_key_ssm_path" {
  type        = string
  description = "SSM Parameter Store path for LANGCHAIN_API_KEY (SecureString)."
  default     = "/medium-agent-factory/prod/LANGCHAIN_API_KEY"
}

variable "min_size" {
  type        = number
  description = "Minimum number of App Runner instances."
  default     = 1
}

variable "max_size" {
  type        = number
  description = "Maximum number of App Runner instances."
  default     = 3
}
