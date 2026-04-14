# =============================================================
# modules/rds/main.tf — PostgreSQL RDS Database
# =============================================================
# This module creates:
#   1. A DB subnet group (tells RDS which subnets it can use)
#   2. A security group (firewall for the database)
#   3. The RDS PostgreSQL instance itself
#
# WHAT IS RDS?
# RDS (Relational Database Service) is a managed database.
# "Managed" means AWS handles:
#   - OS patching
#   - Database engine upgrades
#   - Automated backups
#   - Failover (Multi-AZ)
# You just connect to it like a regular PostgreSQL server.
#
# WHY RDS INSTEAD OF POSTGRESQL IN DOCKER ON EC2?
# You could run PostgreSQL in Docker on your EC2 instance (like
# in development). RDS is better in production because:
#   - Backups happen automatically (you set a retention window)
#   - It can fail over to a standby in another AZ within ~60s
#   - Disk storage auto-expands if you enable it
#   - Metrics (CPU, connections, storage) flow to CloudWatch
# =============================================================

# -----------------------------------------------------------------
# DB SUBNET GROUP
# -----------------------------------------------------------------
# A subnet group tells RDS which subnets it is allowed to use.
# Even for a single-AZ deployment, AWS requires the subnet group
# to span at least 2 Availability Zones.

resource "aws_db_subnet_group" "main" {
  name        = "stock-analytics-db-subnet-group-${var.environment}"
  description = "Subnet group for stock analytics RDS instance"
  subnet_ids  = var.private_subnet_ids # all private subnets (in 2 AZs)

  tags = {
    Name = "stock-analytics-db-subnet-group-${var.environment}"
  }
}

# -----------------------------------------------------------------
# SECURITY GROUP — RDS
# -----------------------------------------------------------------
# The DB security group only allows traffic on port 5432 (PostgreSQL)
# and only from the EC2 security group — not from the internet.
#
# This means: even if someone found out the RDS endpoint, they
# could not connect without being inside the VPC first.

resource "aws_security_group" "rds" {
  name        = "stock-analytics-rds-sg-${var.environment}"
  description = "Security group for stock analytics RDS PostgreSQL instance"
  vpc_id      = var.vpc_id

  # INGRESS: Allow PostgreSQL (port 5432) only from the EC2 instance
  ingress {
    description     = "PostgreSQL from EC2 app server only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ec2_security_group_id] # reference SG, not IP — more robust
  }

  # EGRESS: Allow all outbound (needed for RDS to reach AWS services internally)
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "stock-analytics-rds-sg-${var.environment}"
  }
}

# -----------------------------------------------------------------
# RDS POSTGRESQL INSTANCE
# -----------------------------------------------------------------

resource "aws_db_instance" "postgres" {
  # Unique identifier for this DB instance in AWS
  identifier = "stock-analytics-db-${var.environment}"

  # Database engine
  engine         = "postgres"
  engine_version = "15" # PostgreSQL 15 — LTS, widely supported

  # Instance size — db.t3.micro is free-tier eligible (750 hours/month)
  instance_class = var.instance_class

  # Storage
  allocated_storage     = var.allocated_storage
  storage_type          = "gp2" # General Purpose SSD — good balance of cost/performance
  storage_encrypted     = true  # encrypt data at rest

  # Credentials
  db_name  = var.db_name     # the initial database to create
  username = var.db_username
  password = var.db_password

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false # IMPORTANT: DB is private, not accessible from internet

  # Availability
  # multi_az = true would create a standby in another AZ for automatic failover.
  # Disabled here to stay within free tier (Multi-AZ doubles the cost).
  multi_az = false

  # Backups
  # AWS will automatically take a daily snapshot and retain it for 7 days.
  # You can restore to any point within that window.
  backup_retention_period = 7
  backup_window           = "03:00-04:00" # UTC — low-traffic window

  # Maintenance window — when AWS applies patches/upgrades
  maintenance_window = "Mon:04:00-Mon:05:00"

  # Prevent accidental deletion.
  # When deletion_protection = true, `terraform destroy` will fail with an error.
  # You must first set it to false and apply, THEN destroy.
  # Set to false in dev so you can tear down freely; true in prod.
  deletion_protection = false

  # When true, a final snapshot is taken before deletion.
  # Set to false in dev (we don't need snapshots of test data).
  skip_final_snapshot = true

  tags = {
    Name = "stock-analytics-db-${var.environment}"
  }
}
