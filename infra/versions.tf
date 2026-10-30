terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.25.0, < 7.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0, < 4.0.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}

# CloudFront only accepts certificates issued in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags { tags = local.tags }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  tags = {
    purpose        = "assessment 3"
    "qut-username" = var.qut_username
    project        = "RAGcat"
    student-id     = var.student_id
    environment    = "a3"
  }
  prefix     = "${var.student_id}-ragcat-a3"
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)
  services = {
    api = { cpu = 256, memory = 512, max = 2, requests = var.api_requests_per_target }
    qa  = { cpu = 256, memory = 512, max = 4, requests = var.qa_requests_per_target }
  }
  workers = {
    ingest = { memory = 2048, concurrency = 5, queue = "parse" }
    embed  = { memory = 1024, concurrency = 2, queue = "embed" }
  }
  runtimes = toset(["api", "qa", "ingest", "embed"])
}
