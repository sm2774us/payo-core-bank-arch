# Multi-AZ Postgres for the ledger's system of record. multi_az=true is
# non-negotiable here: an unplanned single-AZ outage of the ledger database
# is an operational incident an examiner will ask about by name.

resource "random_password" "master" {
  length  = 32
  special = false # avoid characters that require extra escaping in connection strings
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name       = "${var.name}-rds-master-credentials"
  kms_key_id = var.kms_key_arn
  tags       = var.tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
  })
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-rds-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "rds" {
  name        = "${var.name}-rds-sg"
  description = "Allow Postgres access only from application security groups"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name}-ledger-db"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.allocated_storage_gb * 3
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_name  = "ledger"
  username = var.master_username
  password = random_password.master.result

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 35 # audit/exam evidence retention, not just DR
  deletion_protection     = true
  copy_tags_to_snapshot   = true

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = var.tags
}
