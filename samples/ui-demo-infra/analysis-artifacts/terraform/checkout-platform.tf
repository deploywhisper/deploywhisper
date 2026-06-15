terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

module "checkout_network" {
  source = "./modules/checkout-network"

  environment = "demo-prod"
  cidr_block  = "10.42.0.0/16"
}

resource "aws_security_group" "checkout_admin" {
  name        = "demo-checkout-admin"
  description = "Administrative access for checkout maintenance"
  vpc_id      = module.checkout_network.vpc_id

  ingress {
    description = "Temporary SSH access for release troubleshooting"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Service     = "checkout-api"
    Environment = "demo-prod"
    Owner       = "platform-demo"
  }
}

resource "aws_db_instance" "checkout" {
  identifier              = "demo-checkout-db"
  engine                  = "postgres"
  instance_class          = "db.t3.medium"
  allocated_storage       = 100
  publicly_accessible     = true
  backup_retention_period = 1
  deletion_protection     = false
  skip_final_snapshot     = true
}

resource "aws_iam_policy" "deploy_runner" {
  name        = "demo-deploy-runner-wide-policy"
  description = "Synthetic deploy runner policy for UI demo review"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["eks:*", "iam:PassRole", "s3:*"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = "demo-checkout-public-assets"

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}
