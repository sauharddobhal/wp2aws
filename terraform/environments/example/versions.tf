terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }

  # Configure your own backend; see backend.tf.example for a starting point.
}

provider "aws" {
  region = var.aws_region
}

# Required by the cdn module: CloudFront's WAF web ACL (scope = CLOUDFRONT) and ACM
# certificate must both exist in us-east-1, regardless of var.aws_region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
