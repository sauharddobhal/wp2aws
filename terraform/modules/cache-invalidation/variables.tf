variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "cloudfront_distribution_id" {
  description = "CloudFront distribution ID the Lambda is allowed to invalidate paths on."
  type        = string
}

variable "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN, used to scope the IAM policy to exactly this distribution."
  type        = string
}

variable "webhook_shared_secret" {
  description = "Shared secret the WordPress publish webhook must send to authenticate. Generate a long random value and store it the same place your WordPress webhook plugin reads its config from; do not commit a real value to source control."
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "Optional email address to notify on Lambda errors (e.g. CloudFront API failures) and to receive failed-invalidation alerts. If null, no SNS topic or CloudWatch alarm is created, errors would only be visible in CloudWatch Logs and the failed-invalidations SQS queue."
  type        = string
  default     = null
}
