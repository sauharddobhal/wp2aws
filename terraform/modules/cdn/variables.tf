variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name of the ALB to use as the dynamic/HTML origin."
  type        = string
}

variable "media_bucket_regional_domain_name" {
  description = "Regional domain name of the S3 media bucket, used as the media origin."
  type        = string
}

variable "domain_aliases" {
  description = "Domain names (CNAMEs) this distribution should respond to, e.g. [\"www.example.com\", \"example.com\"]."
  type        = list(string)
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the domain aliases above. Must be issued in us-east-1, CloudFront only accepts certificates from that region regardless of where the rest of the stack runs."
  type        = string
}

variable "origin_shield_region" {
  description = "AWS region for CloudFront Origin Shield. Should match (or be geographically close to) the region the ALB actually runs in, not necessarily us-east-1."
  type        = string
}

variable "default_html_ttl_seconds" {
  description = "Default CloudFront TTL for HTML pages. This bounds worst-case staleness for content that wasn't caught by the targeted publish-time invalidation; see the cache invalidation Lambda."
  type        = number
  default     = 300
}

variable "max_html_ttl_seconds" {
  type    = number
  default = 600
}

variable "login_rate_limit_per_5min" {
  description = "Maximum requests per 5-minute window per IP to /wp-login.php or /xmlrpc.php before WAF blocks that IP."
  type        = number
  default     = 100
}
