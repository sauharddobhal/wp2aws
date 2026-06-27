output "media_bucket_name" {
  value = aws_s3_bucket.media.id
}

output "media_bucket_arn" {
  value = aws_s3_bucket.media.arn
}

output "media_bucket_regional_domain_name" {
  value = aws_s3_bucket.media.bucket_regional_domain_name
}

output "efs_file_system_id" {
  value = aws_efs_file_system.wp_content.id
}

output "efs_access_point_id" {
  value = aws_efs_access_point.wp_content.id
}
