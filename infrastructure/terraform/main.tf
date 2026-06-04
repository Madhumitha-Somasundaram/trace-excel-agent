terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "trace-terraform-state"
    key            = "trace/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "trace-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Trace"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Variables
variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  default     = "production"
}

variable "app_name" {
  description = "Application name"
  default     = "trace"
}

# VPC and Networking
module "vpc" {
  source = "./modules/vpc"

  app_name    = var.app_name
  environment = var.environment
}

# ECR Repositories
resource "aws_ecr_repository" "backend" {
  name                 = "${var.app_name}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.app_name}-worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.app_name}-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ECS Services
module "backend_service" {
  source = "./modules/ecs-service"

  app_name            = var.app_name
  environment         = var.environment
  service_name        = "backend"
  cluster_id          = aws_ecs_cluster.main.id
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  public_subnet_ids   = module.vpc.public_subnet_ids
  container_image     = "${aws_ecr_repository.backend.repository_url}:latest"
  container_port      = 8000
  cpu                 = 1024
  memory              = 2048
  desired_count       = 2
  min_capacity        = 2
  max_capacity        = 10
  enable_lb           = true
  health_check_path   = "/health"
}

module "worker_service" {
  source = "./modules/ecs-service"

  app_name            = var.app_name
  environment         = var.environment
  service_name        = "worker"
  cluster_id          = aws_ecs_cluster.main.id
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  public_subnet_ids   = module.vpc.public_subnet_ids
  container_image     = "${aws_ecr_repository.worker.repository_url}:latest"
  container_port      = 8080
  cpu                 = 2048
  memory              = 4096
  desired_count       = 3
  min_capacity        = 2
  max_capacity        = 20
  enable_lb           = false
  # Auto-scale based on SQS queue depth
  enable_sqs_scaling  = true
  sqs_queue_name      = "excel-trace-queue"
}

# CloudFront and S3 for Frontend
module "frontend" {
  source = "./modules/frontend"

  app_name           = var.app_name
  environment        = var.environment
  backend_lb_dns     = module.backend_service.load_balancer_dns
}

# Outputs
output "backend_url" {
  value = module.backend_service.load_balancer_dns
}

output "frontend_url" {
  value = module.frontend.cloudfront_domain
}

output "ecr_backend_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_worker_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "ecr_frontend_url" {
  value = aws_ecr_repository.frontend.repository_url
}
