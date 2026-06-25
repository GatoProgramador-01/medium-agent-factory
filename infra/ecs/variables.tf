# FILE: infra/ecs/variables.tf

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
  description = "AWS region for the ECS cluster and associated resources."
  default     = "us-east-1"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy (e.g. 'latest', 'v1.2.0', or a Git SHA)."
  default     = "latest"
}

# ECR repository URL without tag — tag is appended from var.image_tag
# Example: 123456789012.dkr.ecr.us-east-1.amazonaws.com/medium-agent-factory-backend
variable "ecr_repository_url" {
  type        = string
  description = "ECR repository URL (no tag). Tag is appended from var.image_tag."
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

variable "desired_count" {
  type        = number
  description = "Number of ECS task replicas to keep running."
  default     = 1
}

variable "task_cpu" {
  type        = number
  description = "Fargate task CPU units (256=0.25vCPU, 512=0.5vCPU, 1024=1vCPU)."
  default     = 512
}

variable "task_memory" {
  type        = number
  description = "Fargate task memory in MiB."
  default     = 1024
}
