provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "logs" {
  bucket = "myapp-dev-logs"

  tags = {
    Environment = "dev"
    Team        = "platform"
  }
}

resource "aws_instance" "worker" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.small"

  tags = {
    Environment = "dev"
  }
}
