# =============================================================
# modules/rds/variables.tf — RDS Module Inputs
# =============================================================

variable "vpc_id" {
  description = "ID of the VPC where the RDS security group will be created."
  type        = string
}

variable "private_subnet_ids" {
  description = <<-EOT
    List of private subnet IDs for the RDS subnet group.
    AWS requires at least 2 subnets in different Availability Zones
    for RDS, even in single-AZ deployments. This is an AWS constraint.
  EOT
  type = list(string)
}

variable "ec2_security_group_id" {
  description = <<-EOT
    Security group ID of the EC2 app server.
    RDS will allow inbound PostgreSQL connections from this SG only.
    This is more secure than allowing a specific IP (which can change).
  EOT
  type = string
}

variable "instance_class" {
  description = "RDS instance class (e.g. db.t3.micro). db.t3.micro is free-tier eligible."
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Name of the initial database to create."
  type        = string
}

variable "db_username" {
  description = "Master username for database authentication."
  type        = string
}

variable "db_password" {
  description = "Master password for database authentication."
  type      = string
  sensitive = true
}

variable "allocated_storage" {
  description = "Storage size in GB. 20 is the minimum and is free-tier eligible."
  type        = number
  default     = 20
}

variable "environment" {
  description = "Environment name for tagging resources."
  type        = string
}
