# ALB + Auto Scaling Group running Nginx + PHP-FPM. Two complementary scaling policies
# are attached: one on CPU (catches generic load), one on ALB request count per target
# (catches the specific failure mode that matters most here, a cache-miss storm sending
# a burst of uncached requests at the origin). Either one alone misses a class of
# problem the other catches.

data "aws_iam_policy_document" "instance_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.name_prefix}-app-instance-role"
  assume_role_policy = data.aws_iam_policy_document.instance_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

data "aws_iam_policy_document" "instance_app_access" {
  statement {
    sid       = "ReadDbCredentials"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_credentials_secret_arn]
  }

  statement {
    sid    = "MediaBucketReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.media_bucket_arn,
      "${var.media_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "instance_app_access" {
  name   = "${var.name_prefix}-app-instance-policy"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_app_access.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-app-instance-profile"
  role = aws_iam_role.instance.name
}

# --- ALB ---

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = {
    Name = "${var.name_prefix}-alb"
  }
}

resource "aws_lb_target_group" "app" {
  name     = "${var.name_prefix}-app-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = var.health_check_path
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200-399"
  }

  tags = {
    Name = "${var.name_prefix}-app-tg"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# --- Launch template + ASG ---

resource "aws_launch_template" "app" {
  name_prefix   = "${var.name_prefix}-app-"
  image_id      = var.ami_id
  instance_type = var.instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.instance.arn
  }

  vpc_security_group_ids = [var.app_security_group_id]

  user_data = base64encode(templatefile("${path.module}/../../../scripts/bootstrap.sh.tftpl", {
    db_proxy_endpoint        = var.db_proxy_endpoint
    redis_primary_endpoint   = var.redis_primary_endpoint
    redis_reader_endpoint    = var.redis_reader_endpoint
    efs_file_system_id       = var.efs_file_system_id
    efs_access_point_id      = var.efs_access_point_id
    media_bucket_name        = var.media_bucket_name
    aws_region               = var.aws_region
    db_credentials_secret_arn = var.db_credentials_secret_arn
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.name_prefix}-app"
    }
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only, matches the SCP in the landing-zone repo
  }
}

resource "aws_autoscaling_group" "app" {
  name                = "${var.name_prefix}-app-asg"
  vpc_zone_identifier = var.private_app_subnet_ids
  target_group_arns   = [aws_lb_target_group.app.arn]
  health_check_type   = "ELB"

  min_size         = var.min_size
  max_size         = var.max_size
  desired_capacity = var.desired_capacity

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 90
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.name_prefix}-app"
    propagate_at_launch = true
  }
}

resource "aws_autoscaling_policy" "cpu_target_tracking" {
  name                   = "${var.name_prefix}-cpu-target-tracking"
  autoscaling_group_name = aws_autoscaling_group.app.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = var.cpu_target_value
  }
}

resource "aws_autoscaling_policy" "request_count_target_tracking" {
  name                   = "${var.name_prefix}-request-count-target-tracking"
  autoscaling_group_name = aws_autoscaling_group.app.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.this.arn_suffix}/${aws_lb_target_group.app.arn_suffix}"
    }
    target_value = var.request_count_target_value
  }
}
