output "cloudfront_domain_name" {
  description = "Default CloudFront domain. Point your real domain's DNS (CNAME/ALIAS) at this, or at your own domain alias once configured."
  value       = module.cdn.distribution_domain_name
}

output "alb_dns_name" {
  value = module.compute.alb_dns_name
}

output "cache_invalidation_webhook_url" {
  description = "Function URL to configure in your WordPress publish webhook plugin."
  value       = module.cache_invalidation.function_url
}

output "media_bucket_name" {
  value = module.storage.media_bucket_name
}

output "db_proxy_endpoint" {
  value = module.database.proxy_endpoint
}
