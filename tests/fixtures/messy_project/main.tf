terraform {
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "us-east-1"
}

provider "aws" {
  alias  = "west"
  region = "us-west-2"
}

# Suffix keeps bucket names globally unique. NOTE: if this resource's
# address ever changes without a moved block, Terraform recreates it and
# every resource that reads its value gets a *new* random suffix.
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "assets" {
  bucket = "my-app-assets-${random_id.bucket_suffix.hex}"

  tags = {
    Environment = "shared"
    Owner       = "platform-team"
  }
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"

  tags = {
    Name = "web-server"
  }
}

resource "aws_instance" "west_replica" {
  provider      = aws.west
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}

variable "ports" {
  type    = list(number)
  default = [80, 443, 8080]
}

resource "aws_security_group" "app" {
  name = "app-sg"

  dynamic "ingress" {
    for_each = var.ports
    content {
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "by_az" {
  for_each          = toset(data.aws_availability_zones.available.names)
  vpc_id            = "vpc-0123456789abcdef0"
  availability_zone = each.value
  cidr_block        = "10.0.1.0/24"
}

resource "aws_iam_role" "orphan_role" {
  name = "never-referenced-anywhere"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" }
    }
  ]
}
EOF
}
