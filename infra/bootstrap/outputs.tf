# FILE: infra/bootstrap/outputs.tf

output "state_bucket_name" {
  description = "S3 bucket that stores Terraform remote state."
  value       = aws_s3_bucket.state.id
}

output "dynamodb_table_name" {
  description = "DynamoDB table used for Terraform state locking."
  value       = aws_dynamodb_table.locks.name
}

# Paste this block verbatim into infra/app-runner/backend.tf or infra/ecs/backend.tf
output "backend_config" {
  description = "Ready-to-paste backend block for child modules."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.state.id}"
        key            = "medium-agent-factory/<ENV>/terraform.tfstate"
        region         = "${data.aws_region.current.name}"
        dynamodb_table = "${aws_dynamodb_table.locks.name}"
        encrypt        = true
      }
    }
  EOT
}
