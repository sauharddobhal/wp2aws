variable "name_prefix" {
  description = "Prefix applied to all resource names/tags, e.g. \"wp-prod\"."
  type        = string
  default     = "wp-prod"
}

variable "aws_region" {
  description = "Deployment region for everything except the CloudFront-facing WAF/ACM resources, which must be us-east-1 regardless of this value."
  type        = string
  default     = "us-east-1"
}

# --- Networking ---

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "az_count" {
  type    = number
  default = 3
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one per AZ. Recommended false for production."
  type        = bool
  default     = false
}

# --- Storage ---

variable "media_bucket_name" {
  description = "Globally-unique S3 bucket name for media uploads. Must be changed from the placeholder before applying."
  type        = string
}

# --- Database ---

variable "db_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "db_reader_count" {
  type    = number
  default = 1
}

variable "db_deletion_protection" {
  description = "Should be true for any real production database. Default false here only so the example is easy to tear down in testing."
  type        = bool
  default     = false
}

# --- Cache ---

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "redis_num_cache_clusters" {
  type    = number
  default = 2
}

# --- Compute ---

variable "ami_id" {
  description = "AMI ID to launch app-tier instances from. Must be changed from the placeholder before applying; see README for what the bootstrap script expects (Amazon Linux 2023 family)."
  type        = string
}

variable "instance_type" {
  type    = string
  default = "t4g.medium"
}

variable "app_min_size" {
  type    = number
  default = 2
}

variable "app_max_size" {
  type    = number
  default = 6
}

variable "app_desired_capacity" {
  type    = number
  default = 2
}

variable "alb_acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB's HTTPS listener, in var.aws_region (not necessarily us-east-1, that requirement only applies to the CloudFront-facing certificate below)."
  type        = string
}

# --- CDN ---

variable "domain_aliases" {
  description = "Domain names this distribution should respond to, e.g. [\"www.example.com\"]."
  type        = list(string)
}

variable "cloudfront_acm_certificate_arn" {
  description = "ACM certificate ARN for CloudFront. Must be issued in us-east-1 regardless of var.aws_region."
  type        = string
}

# --- Cache invalidation ---

variable "webhook_shared_secret" {
  description = "Shared secret for the WordPress publish webhook. Generate your own long random value, do not use a placeholder in any real deployment."
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "Optional email to notify on cache-invalidation Lambda errors. If null, no CloudWatch alarm is created."
  type        = string
  default     = null
}
