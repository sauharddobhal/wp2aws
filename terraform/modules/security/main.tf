# Security groups for the stack. Notably, the ALB security group does NOT allow
# inbound 80/443 from 0.0.0.0/0; it's restricted to AWS's managed prefix list for
# CloudFront's origin-facing IP ranges, so the ALB only accepts traffic that actually
# came through CloudFront, not direct-to-origin requests that bypass the CDN and WAF
# entirely. This is a real, commonly-skipped hardening step, most reference templates
# just open the ALB to the world and rely on WAF alone.

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "ALB security group, ingress restricted to CloudFront's IP ranges only."
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTPS from CloudFront only"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  ingress {
    description     = "HTTP from CloudFront only (CloudFront still reaches origin over HTTP if configured that way; prefer HTTPS origin in production)"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-alb-sg"
  }
}

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app-sg"
  description = "App tier (Nginx + PHP-FPM) security group, ingress only from the ALB."
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTP from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-app-sg"
  }
}

resource "aws_security_group" "rds_proxy" {
  name        = "${var.name_prefix}-rds-proxy-sg"
  description = "RDS Proxy security group, ingress only from the app tier."
  vpc_id      = var.vpc_id

  ingress {
    description     = "MySQL from app tier"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-rds-proxy-sg"
  }
}

resource "aws_security_group" "aurora" {
  name        = "${var.name_prefix}-aurora-sg"
  description = "Aurora security group, ingress only from RDS Proxy, not directly from the app tier."
  vpc_id      = var.vpc_id

  ingress {
    description     = "MySQL from RDS Proxy"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_proxy.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-aurora-sg"
  }
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "ElastiCache Redis security group, ingress only from the app tier."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from app tier"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-redis-sg"
  }
}

resource "aws_security_group" "efs" {
  name        = "${var.name_prefix}-efs-sg"
  description = "EFS security group, ingress only from the app tier."
  vpc_id      = var.vpc_id

  ingress {
    description     = "NFS from app tier"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-efs-sg"
  }
}
