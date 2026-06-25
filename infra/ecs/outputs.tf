# FILE: infra/ecs/outputs.tf

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer. Point your domain's CNAME here."
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "ARN of the ALB — needed to attach WAF WebACL or additional listeners."
  value       = aws_lb.main.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.main.arn
}

output "service_name" {
  description = "ECS service name — use with `aws ecs update-service` for manual deploys."
  value       = aws_ecs_service.backend.name
}

output "task_definition_arn" {
  description = "Latest registered task definition ARN."
  value       = aws_ecs_task_definition.backend.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name for ECS task logs."
  value       = aws_cloudwatch_log_group.ecs.name
}

output "task_execution_role_arn" {
  description = "IAM role ARN used by ECS control plane (ECR pull + SSM read)."
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_role_arn" {
  description = "IAM role ARN assumed by the running container (application permissions)."
  value       = aws_iam_role.ecs_task.arn
}
