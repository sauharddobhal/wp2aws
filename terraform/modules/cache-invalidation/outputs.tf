output "function_url" {
  description = "Public HTTPS URL for the WordPress publish webhook to call."
  value       = aws_lambda_function_url.this.function_url
}

output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "failed_invalidations_queue_url" {
  description = "Inspect or replay failed invalidation attempts from here."
  value       = aws_sqs_queue.failed_invalidations.url
}
