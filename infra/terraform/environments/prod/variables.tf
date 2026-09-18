variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "environment_name" {
  type    = string
  default = "payo-core-prod"
}

variable "eks_public_access_cidrs" {
  description = "In prod, the EKS API endpoint's public access is restricted to named CIDRs (corp VPN / bastion) instead of 0.0.0.0/0."
  type        = list(string)
  default     = []
}
