variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "allowed_security_group_ids" {
  type = list(string)
}

variable "instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "allocated_storage_gb" {
  type    = number
  default = 100
}

variable "kms_key_arn" {
  type = string
}

variable "master_username" {
  type    = string
  default = "payo_admin"
}

variable "tags" {
  type    = map(string)
  default = {}
}
