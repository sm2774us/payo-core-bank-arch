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

variable "kms_key_arn" {
  type = string
}

variable "kafka_version" {
  type    = string
  default = "3.7.x"
}

variable "broker_instance_type" {
  type    = string
  default = "kafka.m5.large"
}

variable "tags" {
  type    = map(string)
  default = {}
}
