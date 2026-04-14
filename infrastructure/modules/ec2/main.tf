# =============================================================
# modules/ec2/main.tf — EC2 App Server
# =============================================================
# This module creates:
#   1. A security group controlling what traffic is allowed
#   2. An EC2 instance running Amazon Linux 2023
#   3. A user_data script that runs on first boot to install Docker
#
# WHAT IS AN EC2 INSTANCE?
# Think of EC2 (Elastic Compute Cloud) as renting a virtual
# computer from AWS.  You choose the CPU/RAM (instance_type),
# the operating system (AMI), and the storage (EBS volume).
# You pay by the hour — t2.micro is free for 12 months.
# =============================================================

# -----------------------------------------------------------------
# DATA SOURCE: Latest Amazon Linux 2023 AMI
# -----------------------------------------------------------------
# An AMI (Amazon Machine Image) is a pre-built OS snapshot.
# Instead of hardcoding an AMI ID (which changes per region and
# gets outdated), we query AWS for the latest official one.
#
# aws_ami data source filters available AMIs and returns the
# most recent match.

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"] # Only trust official Amazon AMIs

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"] # Amazon Linux 2023 naming pattern
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"] # HVM (Hardware Virtual Machine) is required for modern instance types
  }
}

# -----------------------------------------------------------------
# SECURITY GROUP — EC2
# -----------------------------------------------------------------
# A security group is a virtual firewall.  AWS denies all traffic
# by default.  You write explicit ALLOW rules — anything not in
# the list is automatically blocked.
#
# "ingress" = incoming traffic (to the EC2 instance)
# "egress"  = outgoing traffic (from the EC2 instance)

resource "aws_security_group" "ec2" {
  name        = "stock-analytics-ec2-sg-${var.environment}"
  description = "Security group for the stock analytics EC2 app server"
  vpc_id      = var.vpc_id

  # --- INGRESS RULES (what can reach us) ---

  # SSH on port 22 — restricted to YOUR IP only.
  # This is how you log into the server to deploy or debug.
  # NEVER open this to 0.0.0.0/0 (the whole internet) on a real server.
  ingress {
    description = "SSH from developer IP only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.your_ip_cidr]
  }

  # HTTP on port 8000 — the Python app (FastAPI/Flask) runs here.
  # Open to everyone so users can access the dashboard.
  ingress {
    description = "Application HTTP port"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Grafana on port 3000 — the monitoring dashboard.
  ingress {
    description = "Grafana dashboard"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Prometheus on port 9090 — metrics scraping UI.
  # In production you'd restrict this to internal traffic only.
  ingress {
    description = "Prometheus metrics"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # --- EGRESS RULES (what we can reach) ---

  # Allow all outbound traffic — needed to:
  # - Pull Docker images from Docker Hub
  # - Fetch stock data from Yahoo Finance
  # - Send email alerts via Gmail SMTP
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1" # -1 means "all protocols"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "stock-analytics-ec2-sg-${var.environment}"
  }
}

# -----------------------------------------------------------------
# EC2 INSTANCE
# -----------------------------------------------------------------

resource "aws_instance" "app_server" {
  # The AMI ID from our data source above
  ami = data.aws_ami.amazon_linux_2023.id

  # CPU + RAM type — t2.micro for free tier
  instance_type = var.instance_type

  # Which subnet to launch in (first public subnet)
  subnet_id = var.subnet_id

  # Attach our security group
  vpc_security_group_ids = [aws_security_group.ec2.id]

  # The SSH key pair for login access
  key_name = var.key_pair_name

  # ROOT DISK
  # gp3 is the latest-gen SSD type — faster and cheaper than gp2.
  # 20 GB is enough for our Docker images and application data.
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    delete_on_termination = true # delete disk when instance is terminated (saves cost)
    encrypted             = true # encrypt at rest
  }

  # USER DATA SCRIPT
  # This bash script runs automatically on the FIRST boot of the instance.
  # It's used for "bootstrapping" — installing software before you SSH in.
  # heredoc syntax (<<-EOF ... EOF) allows multi-line strings in Terraform.
  user_data = <<-EOF
    #!/bin/bash
    # Update all system packages first
    dnf update -y

    # Install Docker
    # Amazon Linux 2023 uses dnf (successor to yum) as its package manager
    dnf install -y docker

    # Start the Docker daemon and enable it to start on reboot
    systemctl start docker
    systemctl enable docker

    # Add the ec2-user to the docker group so it can run docker without sudo
    usermod -aG docker ec2-user

    # Install Docker Compose plugin (v2 — runs as "docker compose", not "docker-compose")
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    # Install git so we can clone the project repository
    dnf install -y git

    # Clone the project to the ec2-user's home directory
    # TODO: replace with your actual GitHub repo URL when applying
    # git clone https://github.com/Himanshutiwari15/stock-market-analytics.git \
    #   /home/ec2-user/stock-market-analytics
    # chown -R ec2-user:ec2-user /home/ec2-user/stock-market-analytics

    echo "Bootstrap complete: Docker, Docker Compose, and Git are installed."
  EOF

  tags = {
    Name = "stock-analytics-app-server-${var.environment}"
  }
}
