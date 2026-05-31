terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }

    cloudflare = {
      source = "cloudflare/cloudflare"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "cloudflare" {}

resource "aws_s3_bucket" "mail_bucket" {
  bucket = "ricardo-vc-ses-mailbox"
}

resource "aws_s3_bucket_public_access_block" "mail_bucket_block" {
  bucket = aws_s3_bucket.mail_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_sns_topic" "mail_topic" {
  name = "ses-mail-received"
}

resource "aws_sqs_queue" "mail_queue" {
  name = "ses-mail-queue"
}

resource "aws_sns_topic_subscription" "mail_queue_subscription" {
  topic_arn = aws_sns_topic.mail_topic.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.mail_queue.arn
}

resource "aws_sqs_queue_policy" "mail_queue_policy" {
  queue_url = aws_sqs_queue.mail_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.mail_queue.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.mail_topic.arn
        }
      }
    }]
  })
}

resource "aws_s3_bucket_policy" "allow_ses_write" {
  bucket = aws_s3_bucket.mail_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowSESPuts"
      Effect = "Allow"
      Principal = {
        Service = "ses.amazonaws.com"
      }
      Action   = "s3:PutObject"
      Resource = "${aws_s3_bucket.mail_bucket.arn}/incoming/*"
      Condition = {
        StringEquals = {
          "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
}

data "aws_caller_identity" "current" {}

resource "aws_ses_domain_identity" "domain" {
  domain = var.domain
}

resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = "ses-s3-mailbox-rules"
}

resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_ses_receipt_rule" "store_in_s3" {
  name          = "store-in-s3"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients   = [var.domain]
  enabled      = true
  scan_enabled = true

  s3_action {
    bucket_name       = aws_s3_bucket.mail_bucket.bucket
    object_key_prefix = "incoming/"
    topic_arn         = aws_sns_topic.mail_topic.arn
    position          = 1
  }
}

resource "cloudflare_dns_record" "ses_verification" {
  zone_id = var.cloudflare_zone_id
  name    = "_amazonses.inbox"
  type    = "TXT"
  content = aws_ses_domain_identity.domain.verification_token
  ttl     = 300
}

resource "cloudflare_dns_record" "mx_inbox" {
  zone_id  = var.cloudflare_zone_id
  name     = "inbox"
  type     = "MX"
  content  = "inbound-smtp.us-east-1.amazonaws.com"
  priority = 10
  ttl      = 300
  proxied  = false
}
