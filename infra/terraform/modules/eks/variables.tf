variable "name" {
  type = string
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m6i.large"]
}

variable "node_min_size" {
  type    = number
  default = 3
}

variable "node_max_size" {
  type    = number
  default = 9
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "kms_key_arn" {
  description = "KMS key used to encrypt Kubernetes secrets at rest (envelope encryption) — required for FFIEC/OCC data-at-rest expectations."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
