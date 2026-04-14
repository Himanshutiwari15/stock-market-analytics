# =============================================================
# main.tf — Root Module (Networking + Module Calls)
# =============================================================
# This is the entry point for Terraform.  It creates the core
# networking layer (VPC, subnets, internet gateway, route tables)
# and then calls the ec2 and rds child modules.
#
# ARCHITECTURE OVERVIEW
# ----------------------
#
#   Internet
#      │
#   Internet Gateway (igw)
#      │
#   ┌──┴─────────────────────────────┐
#   │  VPC  10.0.0.0/16              │
#   │                                │
#   │  Public Subnet  10.0.1.0/24    │  ← EC2 app server lives here
#   │  Public Subnet  10.0.2.0/24    │  ← (second AZ for resilience)
#   │                                │
#   │  Private Subnet 10.0.101.0/24  │  ← RDS database lives here
#   │  Private Subnet 10.0.102.0/24  │  ← (second AZ — AWS RDS requires 2)
#   └────────────────────────────────┘
#
# WHAT IS A VPC?
# A Virtual Private Cloud is your own isolated section of AWS's
# network.  Think of it as renting a floor in an office building —
# you can arrange the rooms (subnets) however you like and control
# who can enter (security groups / route tables).
# =============================================================

# -----------------------------------------------------------------
# DATA SOURCES
# -----------------------------------------------------------------
# A "data source" reads existing information from AWS rather than
# creating something new.  Here we fetch the list of Availability
# Zones in our chosen region so we can spread resources across them
# without hardcoding "us-east-1a", "us-east-1b" etc.

data "aws_availability_zones" "available" {
  state = "available" # only return AZs that are currently operational
}

# -----------------------------------------------------------------
# VPC (Virtual Private Cloud)
# -----------------------------------------------------------------
# The VPC is the outer boundary of our entire network.
# enable_dns_hostnames = true means EC2 instances get a
# human-readable DNS name (e.g. ec2-54-1-2-3.compute.amazonaws.com)
# in addition to their IP address.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "stock-analytics-vpc-${var.environment}"
  }
}

# -----------------------------------------------------------------
# INTERNET GATEWAY
# -----------------------------------------------------------------
# The Internet Gateway is the "door" between our VPC and the public
# internet.  Without it, nothing inside the VPC can reach the internet
# and nothing from the internet can reach us.
# It is attached to the VPC, not to individual subnets.

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id # attach to our VPC

  tags = {
    Name = "stock-analytics-igw-${var.environment}"
  }
}

# -----------------------------------------------------------------
# PUBLIC SUBNETS
# -----------------------------------------------------------------
# Subnets are subdivisions of the VPC's IP range.
# Public subnets will have a route to the internet gateway.
# map_public_ip_on_launch = true means any EC2 launched here
# automatically gets a public IP address.
#
# count = length(var.public_subnet_cidrs) creates one subnet
# per entry in the list — in our case, two subnets.
# element(..., count.index) picks the matching CIDR and AZ
# for each iteration.

resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = element(var.public_subnet_cidrs, count.index)
  availability_zone       = element(data.aws_availability_zones.available.names, count.index)
  map_public_ip_on_launch = true # EC2 instances here get a public IP automatically

  tags = {
    Name = "stock-analytics-public-subnet-${count.index + 1}-${var.environment}"
    Type = "public"
  }
}

# -----------------------------------------------------------------
# PRIVATE SUBNETS
# -----------------------------------------------------------------
# Private subnets have NO route to the internet gateway.
# The database lives here — unreachable from the outside world.
# It can only receive connections from resources inside the VPC
# (like our EC2 app server).

resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = element(var.private_subnet_cidrs, count.index)
  availability_zone = element(data.aws_availability_zones.available.names, count.index)
  # No map_public_ip_on_launch — private subnet instances get NO public IP

  tags = {
    Name = "stock-analytics-private-subnet-${count.index + 1}-${var.environment}"
    Type = "private"
  }
}

# -----------------------------------------------------------------
# ROUTE TABLE — PUBLIC
# -----------------------------------------------------------------
# A route table is a set of rules (routes) that determine where
# network traffic is directed.
#
# We create one route table for public subnets with a default route
# (0.0.0.0/0 means "all traffic") pointing to the internet gateway.
# This is what makes a subnet "public".

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"            # all outbound traffic...
    gateway_id = aws_internet_gateway.main.id # ...goes through the internet gateway
  }

  tags = {
    Name = "stock-analytics-public-rt-${var.environment}"
  }
}

# Associate the public route table with each public subnet.
# Without this association, the subnet uses the VPC's default route
# table which has no internet route.

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------
# MODULES
# -----------------------------------------------------------------
# A Terraform module is a reusable block of resources — like a
# Python function or class.  We call our ec2 and rds modules here,
# passing in the values they need as arguments.
#
# source = path to the module directory (relative to this file)
#
# Any variable declared in the module's variables.tf becomes an
# argument you must (or may) pass here.

module "ec2" {
  source = "./modules/ec2"

  # Networking — tell the module which subnet and VPC to use
  vpc_id    = aws_vpc.main.id
  subnet_id = aws_subnet.public[0].id # place EC2 in the first public subnet

  # Instance configuration
  instance_type = var.ec2_instance_type
  key_pair_name = var.ec2_key_pair_name
  your_ip_cidr  = var.your_ip_cidr
  environment   = var.environment
}

module "rds" {
  source = "./modules/rds"

  # Networking — RDS needs a subnet group spanning ≥2 AZs
  vpc_id             = aws_vpc.main.id
  private_subnet_ids = aws_subnet.private[*].id # pass all private subnet IDs

  # Database configuration
  instance_class     = var.db_instance_class
  db_name            = var.db_name
  db_username        = var.db_username
  db_password        = var.db_password
  allocated_storage  = var.db_allocated_storage
  environment        = var.environment

  # Allow the EC2 security group to connect to RDS on port 5432
  # This is the cross-module dependency: EC2 module exports its
  # security group ID, RDS module uses it in its ingress rule.
  ec2_security_group_id = module.ec2.security_group_id
}
