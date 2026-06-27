# S3 bucket for media uploads (read by WordPress via an offload-media-style plugin,
# served to visitors through CloudFront, never directly public) and an EFS filesystem
# for wp-content, so plugins/themes/uploads-in-progress are consistent across every
# instance in the Auto Scaling Group, not just whatever happened to be baked into the
# AMI at build time.

resource "aws_s3_bucket" "media" {
  bucket = var.media_bucket_name
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket policy granting read access only to the specific CloudFront distribution via
# Origin Access Control, not to the public internet directly. The distribution ARN is
# passed in rather than created here, since CDN ownership lives in the cdn module.
data "aws_iam_policy_document" "media_oac" {
  statement {
    sid    = "AllowCloudFrontServicePrincipalReadOnly"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.media.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [var.cloudfront_distribution_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "media" {
  count  = var.cloudfront_distribution_arn != null ? 1 : 0
  bucket = aws_s3_bucket.media.id
  policy = data.aws_iam_policy_document.media_oac.json
}

# --- EFS for wp-content ---

resource "aws_efs_file_system" "wp_content" {
  creation_token = "${var.name_prefix}-wp-content"
  encrypted      = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name = "${var.name_prefix}-wp-content"
  }
}

resource "aws_efs_mount_target" "wp_content" {
  for_each        = toset(var.private_app_subnet_ids)
  file_system_id  = aws_efs_file_system.wp_content.id
  subnet_id       = each.value
  security_groups = [var.efs_security_group_id]
}

resource "aws_efs_access_point" "wp_content" {
  file_system_id = aws_efs_file_system.wp_content.id

  posix_user {
    uid = 33 # www-data on Debian/Ubuntu-based AMIs
    gid = 33
  }

  root_directory {
    path = "/wp-content"
    creation_info {
      owner_uid   = 33
      owner_gid   = 33
      permissions = "0755"
    }
  }

  tags = {
    Name = "${var.name_prefix}-wp-content-ap"
  }
}
