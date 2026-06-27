# CloudFront distribution with Origin Shield in front of the ALB, plus a WAF web ACL
# using AWS's managed WordPress rule set (a real, specific managed rule group AWS
# publishes for exactly this, not a generic ruleset repurposed for WordPress).
#
# IMPORTANT: this module must be instantiated with a provider aliased to us-east-1.
# WAFv2 web ACLs with scope = "CLOUDFRONT" and ACM certificates used by CloudFront both
# have to exist in us-east-1 regardless of which region the rest of the stack runs in.
# See environments/example/main.tf for how the provider alias is wired in.

resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name_prefix}-waf"
  description = "WAF for the WordPress CloudFront distribution."
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "AWS-AWSManagedRulesWordPressRuleSet"
    priority = 0

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesWordPressRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-wordpress-ruleset"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-common-ruleset"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # Rate-based rule specifically for wp-login.php and xmlrpc.php, the two classic
  # WordPress brute-force / amplification targets. A generic rate limit on every path
  # would also throttle legitimate cached traffic; scoping it to these paths is the
  # actual point.
  rule {
    name     = "RateLimitLoginAndXmlrpc"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.login_rate_limit_per_5min
        aggregate_key_type = "IP"

        scope_down_statement {
          or_statement {
            statement {
              byte_match_statement {
                search_string         = "/wp-login.php"
                positional_constraint = "CONTAINS"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
            statement {
              byte_match_statement {
                search_string         = "/xmlrpc.php"
                positional_constraint = "CONTAINS"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-login-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-waf"
    sampled_requests_enabled   = true
  }
}

# --- Origin Access Control for the S3 media origin ---

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "${var.name_prefix}-media-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- CloudFront Origin Shield region ---
# Origin Shield should be in (or near) the region the ALB actually runs in, not
# necessarily us-east-1; pass the deployment region in via var.origin_shield_region.

resource "aws_cloudfront_distribution" "this" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.name_prefix} WordPress distribution"
  aliases         = var.domain_aliases
  web_acl_id      = aws_wafv2_web_acl.this.arn

  origin {
    domain_name = var.alb_dns_name
    origin_id   = "alb-origin"

    custom_origin_config {
      http_port              = 80
      https_port              = 443
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols     = ["TLSv1.2"]
    }

    origin_shield {
      enabled              = true
      origin_shield_region = var.origin_shield_region
    }
  }

  origin {
    domain_name              = var.media_bucket_regional_domain_name
    origin_id                = "media-origin"
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  default_cache_behavior {
    target_origin_id       = "alb-origin"
    viewer_protocol_policy  = "redirect-to-https"
    allowed_methods         = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = var.default_html_ttl_seconds
    max_ttl     = var.max_html_ttl_seconds
  }

  # /wp-admin and wp-login.php must never be cached or this becomes a security and
  # correctness problem (stale admin UI, or one editor's session bleeding into another
  # visitor's cached response). Forward everything through untouched.
  ordered_cache_behavior {
    path_pattern             = "/wp-admin/*"
    target_origin_id        = "alb-origin"
    viewer_protocol_policy  = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      cookies {
        forward = "all"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  ordered_cache_behavior {
    path_pattern            = "/wp-login.php"
    target_origin_id        = "alb-origin"
    viewer_protocol_policy  = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      cookies {
        forward = "all"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  ordered_cache_behavior {
    path_pattern            = "/wp-content/uploads/*"
    target_origin_id        = "media-origin"
    viewer_protocol_policy  = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 86400
    default_ttl = 604800
    max_ttl     = 31536000
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
