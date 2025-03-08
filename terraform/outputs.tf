output "lambda_function_name" {
  description = "The name of the Lambda function"
  value       = aws_lambda_function.puppy_adoption_lambda.function_name
}

output "lambda_function_arn" {
  description = "The ARN of the Lambda function"
  value       = aws_lambda_function.puppy_adoption_lambda.arn
}

output "cloudwatch_event_rule_name" {
  description = "The name of the CloudWatch Event Rule"
  value       = aws_cloudwatch_event_rule.daily_trigger.name
}
