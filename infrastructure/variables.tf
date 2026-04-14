# =============================================================
# variables.tf — Input Variables (Root Module)
# =============================================================
# Variables are Terraform's equivalent of function parameters.
# They make your code reusable — swap var.environment from
# "dev" to "prod" and the same code creates a production stack.
#
# HOW VARIABLES WORK
# -------------------
# You declare them here (type + description + optional default).
# You supply values in terraform.tfvars (never committed) or via
# environment variables prefixed with TF_VAR_ (e.g. TF_VAR_db_password).
#
# Sensitive variables (passwords, keys) should have
#   sensitive = true
# This prevents Terraform from printing them in plan/apply output.
# =============================================================

# -----------------------------------------------------------------
# AWS / Region
# -----------------------------------------------------------------

variable "aws_region" {
  description = "AWS region to deploy all resources into. us-east-1 is cheapest for free-tier."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name. Used in resource names and tags."
  type        = string
  default     = "dev"

  # validation blocks enforce rules at plan time — before anything is created.
  # This prevents typos like "develoment" from causing subtle bugs.
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

# -----------------------------------------------------------------
# Networking
# -----------------------------------------------------------------

variable "vpc_cidr" {
  description = <<-EOT
    CIDR block for the VPC. A CIDR block defines the IP address range
    for the whole network. 10.0.0.0/16 gives us 65,536 IP addresses
    to split across subnets.
  EOT
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = <<-EOT
    CIDR blocks for public subnets. Public subnets have a route to the
    internet via the Internet Gateway — resources here get a public IP.
    We put the EC2 app server here so users can reach it.
    We create two subnets in different Availability Zones (AZs) for
    resilience. AWS requires multi-AZ for RDS.
  EOT
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = <<-EOT
    CIDR blocks for private subnets. Private subnets have NO route to
    the internet. The RDS database lives here — it can only be reached
    from inside the VPC (i.e. from the EC2 app server), never directly
    from the internet. This is a key security practice.
  EOT
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
}

# -----------------------------------------------------------------
# EC2 (App Server)
# -----------------------------------------------------------------

variable "ec2_instance_type" {
  description = <<-EOT
    EC2 instance type. t2.micro is the free-tier eligible type —
    1 vCPU, 1 GB RAM. Enough to run our Docker Compose stack.
    t3.micro is the modern replacement (also free tier in some regions).
  EOT
  type    = string
  default = "t2.micro"
}

variable "ec2_key_pair_name" {
  description = <<-EOT
    Name of an existing AWS Key Pair to attach to the EC2 instance.
    You must create this in the AWS console (EC2 → Key Pairs → Create)
    and download the .pem file BEFORE running terraform apply.
    Without this you cannot SSH into the server.
  EOT
  type    = string
  default = "stock-analytics-keypair"
}

variable "your_ip_cidr" {
  description = <<-EOT
    Your home/office IP address in CIDR notation, e.g. "203.0.113.5/32".
    The /32 means "exactly this one IP address".
    We restrict SSH access to only this IP — if left open (0.0.0.0/0)
    the server will be brute-forced within minutes.
    Find your IP at: https://whatismyip.com
  EOT
  type    = string
  default = "0.0.0.0/0" # TODO: change this to your actual IP before applying!
}

# -----------------------------------------------------------------
# RDS (PostgreSQL Database)
# -----------------------------------------------------------------

variable "db_instance_class" {
  description = <<-EOT
    RDS instance class. db.t3.micro is free-tier eligible —
    2 vCPU, 1 GB RAM. More than enough for our analytics workload.
  EOT
  type    = string
  default = "db.t3.micro"
}

variable "db_name" {
  description = "Name of the PostgreSQL database to create inside RDS."
  type        = string
  default     = "stockdb"
}

variable "db_username" {
  description = "Master username for the RDS PostgreSQL instance."
  type        = string
  default     = "stockadmin"
}

variable "db_password" {
  description = <<-EOT
    Master password for the RDS PostgreSQL instance.
    Mark sensitive = true so Terraform never prints it in terminal output.
    Supply via terraform.tfvars (which is git-ignored) or the
    TF_VAR_db_password environment variable.
  EOT
  type      = string
  sensitive = true # never printed to console or stored in plan files in plaintext
}

variable "db_allocated_storage" {
  description = "Storage size in GB for the RDS instance. 20 GB is the free-tier minimum."
  type        = number
  default     = 20
}
