# ElastiCache Redis replication group, used for two distinct things by the app tier:
# the WordPress object cache (offloading repeated DB queries) and externalized PHP
# sessions. Both are critical to making the Auto Scaling Group actually stateless;
# without this, scaling the app tier in and out would lose sessions and hammer Aurora
# directly for every cacheable query.

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnet-group"
  subnet_ids = var.private_data_subnet_ids
}

resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name_prefix}-redis-params"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru" # evict least-recently-used keys under memory pressure rather than refusing writes; correct default for a cache, wrong for a primary data store
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Redis for WordPress object cache and session storage."
  engine                = "redis"
  engine_version        = var.engine_version
  node_type              = var.node_type
  num_cache_clusters     = var.num_cache_clusters
  parameter_group_name   = aws_elasticache_parameter_group.this.name
  subnet_group_name      = aws_elasticache_subnet_group.this.name
  security_group_ids     = [var.redis_security_group_id]

  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Name = "${var.name_prefix}-redis"
  }
}
