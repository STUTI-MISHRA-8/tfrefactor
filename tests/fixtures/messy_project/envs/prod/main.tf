provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "logs" {
  bucket = "myapp-prod-logs"

  tags = {
    Environment = "prod"
    Team        = "platform"
  }
}

resource "aws_instance" "worker" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "m5.large"

  tags = {
    Environment = "prod"
  }
}
