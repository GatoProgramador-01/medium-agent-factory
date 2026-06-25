# FILE: infra/app-runner/outputs.tf

output "service_url" {
  description = "HTTPS URL for the App Runner service (no protocol prefix needed — always HTTPS)."
  value       = "https://${aws_apprunner_service.backend.service_url}"
}

output "service_arn" {
  description = "ARN of the App Runner service — useful for IAM policies and monitoring."
  value       = aws_apprunner_service.backend.arn
}

output "service_id" {
  description = "App Runner service ID."
  value       = aws_apprunner_service.backend.service_id
}

output "instance_role_arn" {
  description = "ARN of the IAM role assumed by the running container."
  value       = aws_iam_role.app_runner_instance.arn
}
