variable "region" {
  type    = string
  default = "ap-southeast-2"
  validation {
    condition     = var.region == "ap-southeast-2"
    error_message = "CAB432 regional resources must use ap-southeast-2."
  }
}

variable "student_id" {
  type    = string
  default = "n12218642"
  validation {
    condition     = can(regex("^n[0-9]{8}$", var.student_id))
    error_message = "Use the student ID prefix, for example n12218642."
  }
}

variable "qut_username" {
  description = "Verified QUT email for resource ownership tags and the submission YAML."
  type        = string
  validation {
    condition     = can(regex("^[^@]+@qut\\.edu\\.au$", var.qut_username))
    error_message = "Supply your QUT email."
  }
}

variable "cognito_pool_id" {
  description = "Reuse the existing shared-account User Pool. Terraform does not manage the pool."
  type        = string
  validation {
    condition     = can(regex("^ap-southeast-2_[a-zA-Z0-9]+$", var.cognito_pool_id))
    error_message = "Supply an existing Sydney Cognito User Pool ID."
  }
}

variable "existing_cluster_arn" {
  description = "Optional shared ECS cluster ARN. Only new RAGcat services are managed."
  type        = string
  default     = null
  validation {
    condition     = var.existing_cluster_arn == null ? true : can(regex("^arn:aws:ecs:ap-southeast-2:[0-9]{12}:cluster/.+$", var.existing_cluster_arn))
    error_message = "The reused cluster must be in Sydney."
  }
}

variable "existing_network" {
  description = "Optional existing VPC with an IGW and private subnets with outbound AWS API access."
  type = object({
    vpc_id             = string
    public_subnet_ids  = list(string)
    private_subnet_ids = list(string)
  })
  default = null
  validation {
    condition     = var.existing_network == null ? true : length(var.existing_network.public_subnet_ids) >= 2 && length(var.existing_network.private_subnet_ids) >= 2
    error_message = "Supply public/private subnets in at least two availability zones."
  }
}

variable "deploy_workloads" {
  description = "Bootstrap with false, publish both ECR images, then set true."
  type        = bool
  default     = false
}

variable "image_tag" {
  description = "Immutable ECR tag published for both service and worker images."
  type        = string
  default     = "unpublished"
  validation {
    condition     = !var.deploy_workloads || var.image_tag != "unpublished"
    error_message = "Publish images and supply their immutable tag before enabling workloads."
  }
}

variable "embed_dimensions" {
  type    = number
  default = 1024
  validation {
    condition     = contains([256, 512, 1024], var.embed_dimensions)
    error_message = "Titan v2 requires 256, 512, or 1024 dimensions; changing this replaces the vector index."
  }
}

variable "llm_model_id" {
  type    = string
  default = "google.gemma-3-12b-it"
}

variable "vision_model_id" {
  type    = string
  default = "google.gemma-3-12b-it"
}

variable "cache_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "api_requests_per_target" {
  description = "Requests per task per minute; tune using measured load-test results."
  type        = number
  default     = 300
  validation {
    condition     = var.api_requests_per_target > 0
    error_message = "The target must be positive."
  }
}

variable "qa_requests_per_target" {
  type    = number
  default = 60
  validation {
    condition     = var.qa_requests_per_target > 0
    error_message = "The target must be positive."
  }
}

variable "extra_cors_origins" {
  description = "Optional explicitly allowed browser origins for presigned S3 uploads."
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for origin in var.extra_cors_origins : origin != "*"])
    error_message = "Use explicit upload origins, not a wildcard."
  }
}
