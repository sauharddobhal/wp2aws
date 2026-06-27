variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "media_bucket_name" {
  description = "Globally-unique S3 bucket name for media uploads."
  type        = string
}

variable "cloudfront_distribution_arn" {
  description = "ARN of the CloudFront distribution allowed to read from the media bucket via Origin Access Control. Pass null on first apply if creating the bucket and distribution together would create a cycle, then apply again once the distribution exists."
  type        = string
  default     = null
}

variable "private_app_subnet_ids" {
  description = "Private app-tier subnet IDs to create EFS mount targets in, one per subnet/AZ."
  type        = list(string)
}

variable "efs_security_group_id" {
  description = "Security group ID to attach to the EFS mount targets."
  type        = string
}
