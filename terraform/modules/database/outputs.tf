output "cluster_id" {
  value = aws_rds_cluster.this.id
}

output "cluster_endpoint" {
  description = "Writer endpoint of the Aurora cluster. App tier should use the RDS Proxy endpoint instead of this directly; see proxy_endpoint."
  value       = aws_rds_cluster.this.endpoint
}

output "cluster_reader_endpoint" {
  value = aws_rds_cluster.this.reader_endpoint
}

output "proxy_endpoint" {
  description = "RDS Proxy endpoint. The app tier should connect here, not directly to the cluster endpoint."
  value       = aws_db_proxy.this.endpoint
}

output "db_credentials_secret_arn" {
  description = "Secrets Manager ARN holding the master username/password, for the app tier to read at boot."
  value       = aws_secretsmanager_secret.db_credentials.arn
}
