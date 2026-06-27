variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID these security groups belong to."
  type        = string
}
