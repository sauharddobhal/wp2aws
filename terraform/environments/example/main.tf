# Wires networking, security, storage, database, cache, compute, cdn, and
# cache-invalidation together into one deployable WordPress stack.
#
# Note the provider alias: the cdn module's WAF web ACL (scope = CLOUDFRONT) must be
# created in us-east-1 regardless of var.aws_region, see modules/cdn/main.tf for why.

module "networking" {
  source             = "../../modules/networking"
  name_prefix        = var.name_prefix
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  single_nat_gateway = var.single_nat_gateway
}

module "security" {
  source      = "../../modules/security"
  name_prefix = var.name_prefix
  vpc_id      = module.networking.vpc_id
}

module "storage" {
  source                      = "../../modules/storage"
  name_prefix                 = var.name_prefix
  media_bucket_name           = var.media_bucket_name
  private_app_subnet_ids      = module.networking.private_app_subnet_ids
  efs_security_group_id       = module.security.efs_security_group_id
  cloudfront_distribution_arn = module.cdn.distribution_arn
}

module "database" {
  source                      = "../../modules/database"
  name_prefix                 = var.name_prefix
  private_data_subnet_ids     = module.networking.private_data_subnet_ids
  aurora_security_group_id    = module.security.aurora_security_group_id
  rds_proxy_security_group_id = module.security.rds_proxy_security_group_id
  instance_class               = var.db_instance_class
  reader_count                 = var.db_reader_count
  deletion_protection          = var.db_deletion_protection
}

module "cache" {
  source                   = "../../modules/cache"
  name_prefix              = var.name_prefix
  private_data_subnet_ids  = module.networking.private_data_subnet_ids
  redis_security_group_id  = module.security.redis_security_group_id
  node_type                = var.redis_node_type
  num_cache_clusters       = var.redis_num_cache_clusters
}

module "compute" {
  source     = "../../modules/compute"
  name_prefix = var.name_prefix
  vpc_id      = module.networking.vpc_id
  aws_region  = var.aws_region

  public_subnet_ids      = module.networking.public_subnet_ids
  private_app_subnet_ids = module.networking.private_app_subnet_ids
  alb_security_group_id  = module.security.alb_security_group_id
  app_security_group_id  = module.security.app_security_group_id
  alb_acm_certificate_arn = var.alb_acm_certificate_arn

  ami_id        = var.ami_id
  instance_type = var.instance_type
  min_size      = var.app_min_size
  max_size      = var.app_max_size
  desired_capacity = var.app_desired_capacity

  db_proxy_endpoint          = module.database.proxy_endpoint
  db_credentials_secret_arn  = module.database.db_credentials_secret_arn
  redis_primary_endpoint     = module.cache.primary_endpoint_address
  redis_reader_endpoint      = module.cache.reader_endpoint_address
  efs_file_system_id         = module.storage.efs_file_system_id
  efs_access_point_id        = module.storage.efs_access_point_id
  media_bucket_name          = module.storage.media_bucket_name
  media_bucket_arn           = module.storage.media_bucket_arn
}

module "cdn" {
  source = "../../modules/cdn"
  providers = {
    aws = aws.us_east_1
  }

  name_prefix                       = var.name_prefix
  alb_dns_name                      = module.compute.alb_dns_name
  media_bucket_regional_domain_name = module.storage.media_bucket_regional_domain_name
  domain_aliases                    = var.domain_aliases
  acm_certificate_arn               = var.cloudfront_acm_certificate_arn
  origin_shield_region              = var.aws_region
}

module "cache_invalidation" {
  source                      = "../../modules/cache-invalidation"
  name_prefix                 = var.name_prefix
  cloudfront_distribution_id  = module.cdn.distribution_id
  cloudfront_distribution_arn = module.cdn.distribution_arn
  webhook_shared_secret       = var.webhook_shared_secret
  alert_email                 = var.alert_email
}
