output "mail_bucket" {
  value = aws_s3_bucket.mail_bucket.bucket
}

output "sqs_queue_url" {
  value = aws_sqs_queue.mail_queue.url
}

output "ses_domain_verification_token" {
  value = aws_ses_domain_identity.domain.verification_token
}

output "test_email_domain" {
  value = var.domain
}

output "ses_smtp_username" {
  value     = aws_iam_access_key.ses_smtp_sender_key.id
  sensitive = true
}

output "ses_smtp_password" {
  value     = aws_iam_access_key.ses_smtp_sender_key.ses_smtp_password_v4
  sensitive = true
}

output "ses_dkim_tokens" {
  value = aws_ses_domain_dkim.domain.dkim_tokens
}
