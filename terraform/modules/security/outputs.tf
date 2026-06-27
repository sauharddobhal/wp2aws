output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}

output "rds_proxy_security_group_id" {
  value = aws_security_group.rds_proxy.id
}

output "aurora_security_group_id" {
  value = aws_security_group.aurora.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}

output "efs_security_group_id" {
  value = aws_security_group.efs.id
}
