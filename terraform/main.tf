# Use a null_resource to install dependencies
resource "null_resource" "install_dependencies" {
  triggers = {
    # Track changes to both requirements.txt and main.py
    requirements_hash = filemd5("${path.module}/../lambda/requirements.txt")
    lambda_hash       = filemd5("${path.module}/../lambda/main.py")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/lambda_build
      mkdir -p ${path.module}/lambda_build
      cp ${path.module}/../lambda/main.py ${path.module}/lambda_build/
      cp ${path.module}/../lambda/requirements.txt ${path.module}/lambda_build/
      pip install -r ${path.module}/lambda_build/requirements.txt -t ${path.module}/lambda_build/
      rm -f ${path.module}/lambda_build/requirements.txt
    EOT
  }
}

# Update the archive_file data source to use the build directory
data "archive_file" "lambda_zip" {
  depends_on  = [null_resource.install_dependencies]
  type        = "zip"
  source_dir  = "${path.module}/lambda_build"
  output_path = "${path.module}/puppy_adoption_lambda.zip"
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "puppy_adoption_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for Lambda to use SES and CloudWatch Logs
resource "aws_iam_policy" "lambda_policy" {
  name        = "puppy_adoption_lambda_policy"
  description = "IAM policy for Puppy Adoption Lambda"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*",
        Effect   = "Allow"
      },
      {
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ],
        Resource = "*",
        Effect   = "Allow"
      }
    ]
  })
}

# Attach the policy to the role
resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# Lambda function
resource "aws_lambda_function" "puppy_adoption_lambda" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "puppy_adoption_notifier"
  role             = aws_iam_role.lambda_role.arn
  handler          = "main.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size

  environment {
    variables = {
      EMAIL_FROM = var.email_from
      EMAIL_TO   = var.email_to
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_policy_attachment
  ]
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/puppy_adoption_notifier"
  retention_in_days = 14
}

# CloudWatch Event Rule to trigger Lambda daily
resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "daily_puppy_adoption_check"
  description         = "Triggers puppy adoption Lambda function daily"
  schedule_expression = var.schedule_expression
}

# CloudWatch Event Target connecting the rule to the Lambda function
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name
  target_id = "puppy_adoption_lambda"
  arn       = aws_lambda_function.puppy_adoption_lambda.arn
}

# Permission for CloudWatch Events to invoke Lambda
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.puppy_adoption_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
}
