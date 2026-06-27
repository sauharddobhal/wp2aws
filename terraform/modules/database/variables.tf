variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "private_data_subnet_ids" {
  description = "Private data-tier subnet IDs for the DB subnet group and RDS Proxy."
  type        = list(string)
}

variable "aurora_security_group_id" {
  description = "Security group ID to attach to the Aurora cluster."
  type        = string
}

variable "rds_proxy_security_group_id" {
  description = "Security group ID to attach to RDS Proxy."
  type        = string
}

variable "database_name" {
  description = "Initial database name created in the cluster."
  type        = string
  default     = "wordpress"
}

variable "master_username" {
  description = "Master username for the Aurora cluster."
  type        = string
  default     = "wp_admin"
}

variable "engine_version" {
  description = "Aurora MySQL engine version."
  type        = string
  default     = "8.0.mysql_aurora.3.05.2"
}

variable "instance_class" {
  description = "Instance class for both the writer and reader instances."
  type        = string
  default     = "db.r6g.large"
}

variable "reader_count" {
  description = "Number of Aurora reader instances to create, for read scaling."
  type        = number
  default     = 1
}

variable "backup_retention_days" {
  description = "Automated backup retention period in days."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Whether to enable deletion protection on the cluster. Should be true for any real production database; default is false here only so the example environment is easy to tear down in testing."
  type        = bool
  default     = false
}
