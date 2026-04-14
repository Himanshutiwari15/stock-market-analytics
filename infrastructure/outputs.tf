# =============================================================
# outputs.tf — Root Module Outputs
# =============================================================
# Outputs are like return values for a Terraform module.
# After `terraform apply` completes, these values are printed
# to the terminal so you know where your infrastructure is.
#
# They're also useful when:
# - Another Terraform module needs to reference this one
# - A CI/CD script needs to know the server IP to deploy to
# - You want to quickly find your server address without
#   navigating the AWS console
# =============================================================

output "vpc_id" {
  description = "ID of the VPC. Useful for adding more resources to the same network later."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets. Use these when launching additional EC2 instances."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets. Use these when adding more database services."
  value       = aws_subnet.private[*].id
}

# -----------------------------------------------------------------
# EC2 Outputs
# -----------------------------------------------------------------

output "ec2_public_ip" {
  description = <<-EOT
    Public IP address of the EC2 app server.
    Use this to:
      - SSH into the server:  ssh -i ~/.ssh/stock-analytics-keypair.pem ec2-user@<this-ip>
      - Access the app:       http://<this-ip>:8000
      - Access Grafana:       http://<this-ip>:3000
      - Access Prometheus:    http://<this-ip>:9090
  EOT
  value = module.ec2.public_ip
}

output "ec2_instance_id" {
  description = "EC2 instance ID. Use this in the AWS console or with the AWS CLI to manage the server."
  value       = module.ec2.instance_id
}

# -----------------------------------------------------------------
# RDS Outputs
# -----------------------------------------------------------------

output "rds_endpoint" {
  description = <<-EOT
    Connection endpoint for the RDS PostgreSQL database.
    Format: <hostname>:<port>
    Use the hostname portion in your .env as DB_HOST.
    Note: this endpoint is only reachable from within the VPC
    (i.e. from the EC2 instance), not from your laptop.
  EOT
  value = module.rds.endpoint
}

output "rds_port" {
  description = "Port the RDS PostgreSQL instance listens on (5432 by default)."
  value       = module.rds.port
}

output "rds_database_name" {
  description = "Name of the PostgreSQL database created inside RDS."
  value       = module.rds.database_name
}

# -----------------------------------------------------------------
# Deployment instructions printed after apply
# -----------------------------------------------------------------

output "next_steps" {
  description = "What to do after terraform apply completes."
  value       = <<-EOT

    =========================================================
    Deployment complete!
    =========================================================

    1. Copy your .env file to the server:
       scp -i ~/.ssh/stock-analytics-keypair.pem .env ec2-user@${module.ec2.public_ip}:~/stock-market-analytics/

    2. SSH into the server:
       ssh -i ~/.ssh/stock-analytics-keypair.pem ec2-user@${module.ec2.public_ip}

    3. Start the application (Docker is pre-installed by user_data):
       cd stock-market-analytics && docker compose up -d

    4. Access your services:
       - App:        http://${module.ec2.public_ip}:8000
       - Grafana:    http://${module.ec2.public_ip}:3000
       - Prometheus: http://${module.ec2.public_ip}:9090

    5. Update DB_HOST in your .env to the RDS endpoint:
       ${module.rds.endpoint}

    =========================================================
  EOT
}
