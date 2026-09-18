terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state is intentionally NOT hardcoded here — a showcase repo should
  # not ship a bucket name that looks like a real account. Configure via
  # `terraform init -backend-config=backend.hcl` in a real deployment.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "payo-core-bank"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}
