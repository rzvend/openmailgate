variable "domain" {
  default = "openmailgate.ricardo.vc"
}

variable "mail_bucket_name" {
  default = "ses-openmailgate-mailbox"
}

variable "sqs_queue_name" {
  default = "ses-openmailgate-incoming"
}

variable "cloudflare_zone_id" {
  default = "02374416228efbe4b59fc547d0ce0e77"
}
