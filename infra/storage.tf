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

resource "aws_s3_bucket" "main" {
  for_each      = toset(["files", "web"])
  bucket        = "${local.prefix}-${local.account_id}-${each.key}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "main" {
  for_each                = aws_s3_bucket.main
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_ownership_controls" "main" {
  for_each = aws_s3_bucket.main
  bucket   = each.value.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_policy" "files" {
  bucket = aws_s3_bucket.main["files"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.main["files"].arn, "${aws_s3_bucket.main["files"].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_cors_configuration" "files" {
  bucket = aws_s3_bucket.main["files"].id
  cors_rule {
    allowed_origins = concat(["https://${aws_cloudfront_distribution.main.domain_name}"], var.extra_cors_origins)
    allowed_methods = ["POST", "GET", "HEAD"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_notification" "files" {
  bucket      = aws_s3_bucket.main["files"].id
  eventbridge = true
}

resource "aws_s3vectors_vector_bucket" "main" {
  vector_bucket_name = "${local.prefix}-${local.account_id}-vectors"
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
