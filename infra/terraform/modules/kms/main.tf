variable "name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

# One CMK reused across RDS, EKS secrets, Secrets Manager, and the
# reconciliation-worker's evidence-signing key material. A single, auditable
# key with automatic rotation is easier to defend to an examiner than a
# scattered set of ad-hoc encryption mechanisms per service.
resource "aws_kms_key" "this" {
  description             = "PAYO core bank CMK — RDS, EKS secrets, evidence signing"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name}-core-bank"
  target_key_id = aws_kms_key.this.key_id
}

output "key_arn" {
  value = aws_kms_key.this.arn
}

output "key_id" {
  value = aws_kms_key.this.key_id
}
