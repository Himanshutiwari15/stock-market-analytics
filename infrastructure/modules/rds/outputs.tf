# =============================================================
# modules/rds/outputs.tf — RDS Module Outputs
# =============================================================

output "endpoint" {
  description = <<-EOT
    Connection endpoint for the RDS instance.
    Format: <hostname>:5432
    Use the hostname as DB_HOST in your application's .env file.
    Remember: this is only reachable from inside the VPC.
  EOT
  value = aws_db_instance.postgres.endpoint
}

output "port" {
  description = "Port the PostgreSQL instance listens on (always 5432 for PostgreSQL)."
  value       = aws_db_instance.postgres.port
}

output "database_name" {
  description = "Name of the database created inside RDS."
  value       = aws_db_instance.postgres.db_name
}

output "instance_identifier" {
  description = "RDS instance identifier. Used in the AWS console and CLI commands."
  value       = aws_db_instance.postgres.identifier
}

output "security_group_id" {
  description = "ID of the RDS security group. Useful if you need to add more ingress rules later."
  value       = aws_security_group.rds.id
}
