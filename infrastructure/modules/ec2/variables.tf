# =============================================================
# modules/ec2/variables.tf — EC2 Module Inputs
# =============================================================
# These are the "parameters" that the root module must pass
# when it calls this module (in infrastructure/main.tf).
# =============================================================

variable "vpc_id" {
  description = "ID of the VPC where the security group will be created."
  type        = string
}

variable "subnet_id" {
  description = "ID of the public subnet where the EC2 instance will be launched."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type (e.g. t2.micro). t2.micro is free-tier eligible."
  type        = string
  default     = "t2.micro"
}

variable "key_pair_name" {
  description = "Name of an existing AWS Key Pair for SSH access."
  type        = string
}

variable "your_ip_cidr" {
  description = "Your IP in CIDR notation for SSH access (e.g. 203.0.113.5/32)."
  type        = string
}

variable "environment" {
  description = "Environment name for tagging resources."
  type        = string
}
