# ── IAM user + credentials for the local SMTP → SES relay ────────────────
# After apply, get credentials with:
#   terraform output -raw ses_smtp_username
#   terraform output -raw ses_smtp_password
# Then set them in .env:
#   SES_SMTP_USERNAME=<output>
#   SES_SMTP_PASSWORD=<output>

resource "aws_iam_user" "ses_smtp_sender" {
  name = "ses-s3-mailbox-smtp-sender"
}

resource "aws_iam_user_policy" "ses_smtp_sender_policy" {
  name = "ses-send-email"
  user = aws_iam_user.ses_smtp_sender.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ses:SendRawEmail",
        "ses:SendEmail",
      ]
      Resource = aws_ses_domain_identity.domain.arn
    }]
  })
}

resource "aws_iam_access_key" "ses_smtp_sender_key" {
  user = aws_iam_user.ses_smtp_sender.name
}
