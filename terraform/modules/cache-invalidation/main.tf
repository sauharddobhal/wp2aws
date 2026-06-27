# Packages and deploys the cache-invalidation Lambda from scripts/cache-invalidation-lambda,
# fronted by a Lambda Function URL (no API Gateway needed for a single webhook endpoint;
# Function URLs are the right-sized tool here). Auth type is NONE at the Function URL
# level, the shared-secret check inside the handler is what actually gates access, since
# a WordPress webhook plugin can't easily do SigV4-signed requests.

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../scripts/cache-invalidation-lambda"
  output_path = "${path.module}/.build/cache-invalidation-lambda.zip"
  excludes    = ["tests", "requirements.txt", "__pycache__"]
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-cache-invalidation-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Scoped to exactly this distribution, not "cloudfront:*" on "*"; a webhook function
# compromised by a leaked shared secret should only be able to invalidate cache, not
# touch any other CloudFront distribution in the account.
data "aws_iam_policy_document" "lambda_invalidation_access" {
  statement {
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [var.cloudfront_distribution_arn]
  }
}

resource "aws_iam_role_policy" "lambda_invalidation_access" {
  name   = "${var.name_prefix}-cache-invalidation-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_invalidation_access.json
}

# --- Failure capture ---
# This function is invoked via a Lambda Function URL, which uses synchronous
# (RequestResponse) invocation. Lambda's automatic async failure handling
# (Destinations, the built-in DLQ config) only applies to asynchronous invocations and
# would simply never fire here, configuring it would look like a safety feature while
# doing nothing. Instead, the handler itself catches a CloudFront API failure and
# pushes it to this queue before returning the error response; see handler.py.

resource "aws_sqs_queue" "failed_invalidations" {
  name                      = "${var.name_prefix}-failed-invalidations"
  message_retention_seconds = 1209600 # 14 days
}

data "aws_iam_policy_document" "failed_invalidations_send" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.failed_invalidations.arn]
  }
}

resource "aws_iam_role_policy" "failed_invalidations_send" {
  name   = "${var.name_prefix}-failed-invalidations-send"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.failed_invalidations_send.json
}

resource "aws_sns_topic" "alerts" {
  count = var.alert_email != null ? 1 : 0
  name  = "${var.name_prefix}-cache-invalidation-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alert_email != null ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  count               = var.alert_email != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-cache-invalidation-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.this.function_name
  }

  alarm_actions = [aws_sns_topic.alerts[0].arn]
  ok_actions    = [aws_sns_topic.alerts[0].arn]
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.name_prefix}-cache-invalidation"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      CLOUDFRONT_DISTRIBUTION_ID    = var.cloudfront_distribution_id
      WEBHOOK_SHARED_SECRET         = var.webhook_shared_secret
      FAILED_INVALIDATIONS_QUEUE_URL = aws_sqs_queue.failed_invalidations.url
    }
  }
}

resource "aws_lambda_function_url" "this" {
  function_name      = aws_lambda_function.this.function_name
  authorization_type = "NONE"
}
