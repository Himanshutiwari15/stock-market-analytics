# =============================================================
# providers.tf — Terraform Provider Configuration
# =============================================================
# A "provider" is a plugin that lets Terraform talk to a cloud
# platform.  Here we configure the AWS provider and tell
# Terraform exactly which version it is allowed to use.
#
# HOW TERRAFORM VERSIONING WORKS
# --------------------------------
# Terraform itself has a version (the CLI tool you install).
# Each provider also has its own version.  Pinning both ensures
# that running `terraform init` six months from now gives the
# exact same behaviour as it does today.
#
# The "~>" operator means "allow patch upgrades but not major
# or minor ones".  So ~> 5.0 allows 5.0.1, 5.1.2 etc. but
# NOT 6.0.0.
# =============================================================

terraform {
  # Minimum Terraform CLI version required to use this code.
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws" # Official AWS provider from the HashiCorp registry
      version = "~> 5.0"        # Lock to AWS provider v5.x
    }
  }

  # -----------------------------------------------------------------
  # REMOTE STATE BACKEND (S3)
  # -----------------------------------------------------------------
  # Terraform stores a "state file" that tracks what infrastructure
  # it created.  By default it stores this locally (terraform.tfstate).
  # That is fine for experiments, but in a team — or in CI/CD — you
  # store state remotely so everyone shares the same view.
  #
  # We use an S3 bucket + DynamoDB table for state locking.
  # This block is COMMENTED OUT because you don't have an AWS account
  # yet.  When you do, you'll:
  #   1. Create an S3 bucket called "stock-analytics-tfstate-<yourname>"
  #   2. Create a DynamoDB table called "stock-analytics-tflock"
  #   3. Uncomment this block and run: terraform init
  #
  # backend "s3" {
  #   bucket         = "stock-analytics-tfstate-<yourname>"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "stock-analytics-tflock"  # prevents two people applying at once
  #   encrypt        = true                       # state file is encrypted at rest
  # }
}

# -----------------------------------------------------------------
# AWS PROVIDER CONFIGURATION
# -----------------------------------------------------------------
# This block configures the AWS provider with the target region.
# The region is read from a variable (defined in variables.tf)
# so you can deploy to different regions without editing this file.
#
# AUTHENTICATION: The provider reads credentials from the standard
# AWS credential chain:
#   1. Environment variables: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
#   2. ~/.aws/credentials file (created by `aws configure`)
#   3. EC2 instance profile (when running on AWS)
#
# NEVER hardcode access keys here.  If a key is in a .tf file and
# you push to GitHub, bots find it within seconds and rack up bills.
# -----------------------------------------------------------------
provider "aws" {
  region = var.aws_region

  # Tag every resource created by Terraform with these labels.
  # This makes it easy to find all resources in the AWS console
  # and to know which project they belong to.
  default_tags {
    tags = {
      Project     = "stock-market-analytics"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
