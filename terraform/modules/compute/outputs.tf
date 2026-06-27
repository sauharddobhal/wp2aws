output "alb_dns_name" {
  description = "ALB DNS name, used as the CloudFront origin domain."
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  value = aws_lb.this.arn
}

output "autoscaling_group_name" {
  value = aws_autoscaling_group.app.name
}
