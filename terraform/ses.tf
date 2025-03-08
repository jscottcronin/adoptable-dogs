# Verify sender email identity
resource "aws_ses_email_identity" "sender" {
  email = var.email_from

  # Add a lifecycle block to force recreation
  lifecycle {
    create_before_destroy = true
  }
}

# Verify recipient email identity
resource "aws_ses_email_identity" "recipients" {
  for_each = toset(var.email_to)
  email    = each.value

  # Add a lifecycle block to force recreation
  lifecycle {
    create_before_destroy = true
  }
}

# Output email identities 
output "sender_email_identity" {
  value = aws_ses_email_identity.sender.email
}

output "recipient_email_identities" {
  value = [for identity in aws_ses_email_identity.recipients : identity.email]
}
