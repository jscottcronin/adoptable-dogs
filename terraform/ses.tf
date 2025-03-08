# Verify sender email identity
resource "aws_ses_email_identity" "sender" {
  email = var.email_from
}

# Verify recipient email identity
resource "aws_ses_email_identity" "recipient" {
  email = var.email_to
}

# Output email identities 
output "sender_email_identity" {
  value = aws_ses_email_identity.sender.email
}

output "recipient_email_identity" {
  value = aws_ses_email_identity.recipient.email
}
