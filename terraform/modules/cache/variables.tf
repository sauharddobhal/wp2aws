variable "name_prefix" {
  description = "Prefix applied to all resource names/tags."
  type        = string
}

variable "private_data_subnet_ids" {
  description = "Private data-tier subnet IDs for the Redis subnet group."
  type        = list(string)
}

variable "redis_security_group_id" {
  description = "Security group ID to attach to the Redis replication group."
  type        = string
}

variable "node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.r6g.large"
}

variable "num_cache_clusters" {
  description = "Number of cache clusters (nodes) in the replication group. 1 disables automatic failover; 2+ enables Multi-AZ with automatic failover, recommended for production."
  type        = number
  default     = 2
}

variable "engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}
