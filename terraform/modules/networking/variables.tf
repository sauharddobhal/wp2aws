variable "name_prefix" {
  description = "Prefix applied to all resource names/tags, e.g. \"wp-prod\"."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC. Subnets are carved out of this as /24s."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across. 3 is the recommended minimum for production."
  type        = number
  default     = 3
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one per AZ. Cheaper, but a single point of failure for outbound internet access from private subnets. Recommended false for production."
  type        = bool
  default     = false
}
