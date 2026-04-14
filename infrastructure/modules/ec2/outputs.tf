# =============================================================
# modules/ec2/outputs.tf — EC2 Module Outputs
# =============================================================
# These values are "exported" from this module so the root
# module (main.tf) and other modules can use them.
#
# For example, the RDS module needs ec2_security_group_id so it
# can create a rule allowing the EC2 server to connect to the DB.
# =============================================================

output "instance_id" {
  description = "ID of the EC2 instance (e.g. i-0abc123def456789). Use in the AWS console."
  value       = aws_instance.app_server.id
}

output "public_ip" {
  description = "Public IPv4 address of the EC2 instance. Use for SSH and browser access."
  value       = aws_instance.app_server.public_ip
}

output "public_dns" {
  description = "Public DNS hostname of the EC2 instance (alternative to the IP address)."
  value       = aws_instance.app_server.public_dns
}

output "security_group_id" {
  description = <<-EOT
    ID of the EC2 security group.
    The RDS module uses this to allow inbound PostgreSQL traffic
    from the EC2 instance only — not from the whole internet.
  EOT
  value = aws_security_group.ec2.id
}
