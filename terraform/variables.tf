variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "email_from" {
  description = "Email address to send notifications from (must be verified in SES)"
  type        = string
  default     = "j.scott.cronin@gmail.com"
}

variable "email_to" {
  description = "Email address to send notifications to"
  type        = string
  default     = "j.scott.cronin@gmail.com"
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression for when to run the Lambda"
  type        = string
  default     = "cron(0 13,17,20 * * ? *)" # Runs at 8am, 12pm, and 3pm CST (converted to UTC)
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 256
}
