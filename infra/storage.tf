resource "aws_dynamodb_table" "main" {
  name         = "${local.prefix}-data"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  dynamic "attribute" {
    for_each = toset(["PK", "SK", "GSI1PK", "GSI1SK"])
    content {
      name = attribute.value
      type = "S"
    }
  }
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

# Both buckets are created by hand (private, public access blocked, AES256): the student role is denied
# s3:PutBucketNotification, s3:PutBucketPolicy and s3:PutEncryptionConfiguration, so Terraform only reads them.
# files: EventBridge upload notification is enabled in the console.
# web: the CloudFront OAC bucket policy is pasted in the console once the distribution exists.
data "aws_s3_bucket" "files" {
  bucket = "${var.student_id}-a3-files"
}

data "aws_s3_bucket" "web" {
  bucket = "${var.student_id}-a3-web"
}

resource "aws_s3_bucket_cors_configuration" "files" {
  bucket = data.aws_s3_bucket.files.id
  cors_rule {
    allowed_origins = concat(["https://${aws_cloudfront_distribution.main.domain_name}"], var.extra_cors_origins)
    allowed_methods = ["POST", "GET", "HEAD"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3vectors_vector_bucket" "main" {
  vector_bucket_name = "${local.prefix}-vectors"
  force_destroy      = false
  encryption_configuration { sse_type = "AES256" }
}

resource "aws_s3vectors_index" "passages" {
  vector_bucket_name = aws_s3vectors_vector_bucket.main.vector_bucket_name
  index_name         = "passages"
  data_type          = "float32"
  dimension          = var.embed_dimensions
  distance_metric    = "cosine"
  metadata_configuration {
    non_filterable_metadata_keys = ["document_title", "label", "text", "section", "context", "page", "para", "boxes", "edited"]
  }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.prefix}-cache"
  subnet_ids = local.private_subnets
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = "${local.prefix}-cache"
  description                = "Shared Assistant configuration, query vectors, and answer cache"
  engine                     = "valkey"
  engine_version             = "8.0"
  node_type                  = var.cache_node_type
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = local.cache_sgs
  apply_immediately          = true
  port                       = 6379
}
