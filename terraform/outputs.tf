output "mail_bucket" {
  value = aws_s3_bucket.mail_bucket.bucket
}

output "sqs_queue_url" {
  value = aws_sqs_queue.mail_queue.url
}

output "sns_topic_arn" {
  value = aws_sns_topic.mail_topic.arn
}

output "ses_domain_verification_token" {
  value = aws_ses_domain_identity.domain.verification_token
}

output "test_email_domain" {
  value = var.domain
}
