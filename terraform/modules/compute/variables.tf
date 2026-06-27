variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the ALB."
  type        = list(string)
}

variable "private_app_subnet_ids" {
  description = "Private app-tier subnets for the Auto Scaling Group."
  type        = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "app_security_group_id" {
  type = string
}

variable "alb_acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener. Must be in the same region as the ALB (not necessarily us-east-1, that requirement is only for the CloudFront-facing certificate)."
  type        = string
}

variable "ami_id" {
  description = "AMI to launch. Recommended: a current Amazon Linux 2023 ARM64 AMI for Graviton instances, with Nginx/PHP-FPM either baked in or installed by the bootstrap script."
  type        = string
}

variable "instance_type" {
  description = "Instance type. Defaults to a Graviton (ARM) instance for better price/performance at this traffic volume."
  type        = string
  default     = "t4g.medium"
}

variable "health_check_path" {
  type    = string
  default = "/"
}

variable "min_size" {
  type    = number
  default = 2
}

variable "max_size" {
  type    = number
  default = 6
}

variable "desired_capacity" {
  type    = number
  default = 2
}

variable "cpu_target_value" {
  description = "Target average CPU utilization percentage for the CPU-based scaling policy."
  type        = number
  default     = 60
}

variable "request_count_target_value" {
  description = "Target ALB requests per target per minute for the request-count-based scaling policy. This is the policy that actually catches a cache-miss storm; tune it down if cache-miss requests are expensive (e.g. uncached search results) relative to cache hits."
  type        = number
  default     = 1000
}

# --- Values wired in from other modules, passed through to the bootstrap template ---

variable "db_proxy_endpoint" {
  type = string
}

variable "db_credentials_secret_arn" {
  type = string
}

variable "redis_primary_endpoint" {
  type = string
}

variable "redis_reader_endpoint" {
  type = string
}

variable "efs_file_system_id" {
  type = string
}

variable "efs_access_point_id" {
  type = string
}

variable "media_bucket_name" {
  type = string
}

variable "media_bucket_arn" {
  type = string
}
