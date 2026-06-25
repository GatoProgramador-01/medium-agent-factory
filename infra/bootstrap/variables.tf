# FILE: infra/bootstrap/variables.tf

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
  description = "AWS region where bootstrap resources are created."
  default     = "us-east-1"
}
