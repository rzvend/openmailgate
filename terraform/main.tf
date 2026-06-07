terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }

    cloudflare = {
      source = "cloudflare/cloudflare"
    }

    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  backend "local" {
    path = "/app/state/iac/terraform.tfstate"
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "cloudflare" {}

locals {
  mail_prefix = element(split(".", var.domain), 0)

  effective_custom_mail_from_domain = (
    var.custom_mail_from_domain != null && var.custom_mail_from_domain != ""
    ? var.custom_mail_from_domain
    : "mail.${var.domain}"
  )
}

data "cloudflare_zone" "this" {
  zone_id = var.cloudflare_zone_id
}

resource "aws_s3_bucket" "mail_bucket" {
  bucket = var.mail_bucket_name
}

resource "aws_s3_bucket_public_access_block" "mail_bucket_block" {
  bucket = aws_s3_bucket.mail_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_sqs_queue" "mail_queue" {
  name = var.sqs_queue_name
}

resource "aws_sqs_queue_policy" "mail_queue_policy" {
  queue_url = aws_sqs_queue.mail_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "s3.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.mail_queue.arn
      Condition = {
        ArnLike = {
          "aws:SourceArn" = aws_s3_bucket.mail_bucket.arn
        }
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
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
  rule_set_name = var.rule_set_name
}

resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_ses_receipt_rule" "store_in_s3" {
  name          = var.receipt_rule_name
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = [var.domain]
  enabled       = true
  scan_enabled  = true

  s3_action {
    bucket_name       = aws_s3_bucket.mail_bucket.bucket
    object_key_prefix = "incoming/"
    position          = 1
  }
}

resource "cloudflare_dns_record" "ses_verification" {
  zone_id = var.cloudflare_zone_id
  name    = "_amazonses.${local.mail_prefix}"
  type    = "TXT"
  content = aws_ses_domain_identity.domain.verification_token
  ttl     = 300
}

resource "cloudflare_dns_record" "mx_inbox" {
  zone_id  = var.cloudflare_zone_id
  name     = local.mail_prefix
  type     = "MX"
  content  = "inbound-smtp.us-east-1.amazonaws.com"
  priority = 10
  ttl      = 300
  proxied  = false
}

# ── Easy DKIM — sign outgoing mail with the domain's own DKIM key ────────
resource "aws_ses_domain_dkim" "domain" {
  domain = aws_ses_domain_identity.domain.domain
}

resource "cloudflare_dns_record" "ses_dkim" {
  count   = 3
  zone_id = var.cloudflare_zone_id
  name    = "${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}._domainkey.${local.mail_prefix}"
  type    = "CNAME"
  content = "${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}.dkim.amazonses.com"
  ttl     = 300
  proxied = false
}

# ── Custom MAIL FROM Domain ─────────────────────────────────────────────
resource "time_sleep" "wait_ses_identity" {
  depends_on      = [aws_ses_domain_identity.domain]
  create_duration = "20s"
}

resource "aws_ses_domain_mail_from" "this" {
  domain           = aws_ses_domain_identity.domain.domain
  mail_from_domain = local.effective_custom_mail_from_domain
  depends_on       = [time_sleep.wait_ses_identity]
}

resource "cloudflare_dns_record" "mail_from_mx" {
  zone_id  = var.cloudflare_zone_id
  name     = replace(local.effective_custom_mail_from_domain, ".${data.cloudflare_zone.this.name}", "")
  type     = "MX"
  content  = "feedback-smtp.us-east-1.amazonses.com"
  priority = 10
  ttl      = 300
  proxied  = false
}

resource "cloudflare_dns_record" "mail_from_spf" {
  zone_id = var.cloudflare_zone_id
  name    = replace(local.effective_custom_mail_from_domain, ".${data.cloudflare_zone.this.name}", "")
  type    = "TXT"
  content = "v=spf1 include:amazonses.com ~all"
  ttl     = 300
}

# ── S3 Bucket Notification → SQS (direct, no SNS) ─────────────────────────
resource "aws_s3_bucket_notification" "mail_bucket_notification" {
  bucket = aws_s3_bucket.mail_bucket.id

  queue {
    queue_arn     = aws_sqs_queue.mail_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "incoming/"
  }
}
