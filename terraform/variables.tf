variable "domain" {
  default = ""
}

variable "mail_bucket_name" {
  default = "ses-openmailgate-mailbox"
}

variable "sqs_queue_name" {
  default = "ses-openmailgate-incoming"
}

variable "resource_suffix" {
  default = ""
}

variable "rule_set_name" {
  default = "ses-s3-mailbox-rules"
}

variable "receipt_rule_name" {
  default = "store-in-s3"
}

variable "smtp_iam_user" {
  default = "ses-s3-mailbox-smtp-sender"
}

variable "cloudflare_zone_id" {
  default = "02374416228efbe4b59fc547d0ce0e77"
}
