module "kms" {
  source = "../../modules/kms"
  name   = var.environment_name
  tags   = { Environment = "prod" }
}

module "vpc" {
  source               = "../../modules/vpc"
  name                 = var.environment_name
  azs                  = var.azs
  public_subnet_cidrs  = ["10.30.0.0/24", "10.30.1.0/24", "10.30.2.0/24"]
  private_subnet_cidrs = ["10.30.10.0/24", "10.30.11.0/24", "10.30.12.0/24"]
  tags                 = { Environment = "prod" }
}

module "eks" {
  source              = "../../modules/eks"
  name                = var.environment_name
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn         = module.kms.key_arn
  node_min_size       = 3
  node_desired_size   = 6
  node_max_size       = 12
  node_instance_types = ["m6i.xlarge"]
  tags                = { Environment = "prod" }
}

resource "aws_security_group" "app" {
  name        = "${var.environment_name}-app-sg"
  description = "Security group attached to ledger-core/sanctions-screening pods"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Environment = "prod" }
}

module "rds" {
  source                     = "../../modules/rds"
  name                       = var.environment_name
  vpc_id                     = module.vpc.vpc_id
  private_subnet_ids         = module.vpc.private_subnet_ids
  allowed_security_group_ids = [aws_security_group.app.id]
  kms_key_arn                = module.kms.key_arn
  instance_class             = "db.r6g.2xlarge"
  allocated_storage_gb       = 500
  tags                       = { Environment = "prod" }
}

module "msk" {
  source                     = "../../modules/msk"
  name                       = var.environment_name
  vpc_id                     = module.vpc.vpc_id
  private_subnet_ids         = module.vpc.private_subnet_ids
  allowed_security_group_ids = [aws_security_group.app.id]
  kms_key_arn                = module.kms.key_arn
  broker_instance_type       = "kafka.m5.xlarge"
  tags                       = { Environment = "prod" }
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "rds_endpoint" {
  value = module.rds.endpoint
}
