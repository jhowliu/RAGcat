resource "aws_lb" "main" {
  name               = "${local.prefix}-alb"
  internal           = true
  load_balancer_type = "application"
  subnets            = local.private_subnets
  security_groups    = [aws_security_group.alb.id]
  idle_timeout       = 60 # Uvicorn keep-alive is 75s, longer than the ALB's connection reuse window.
}

resource "aws_lb_target_group" "main" {
  for_each             = local.services
  name                 = "${local.prefix}-${each.key}"
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = local.vpc_id
  deregistration_delay = 60
  health_check {
    path    = "/healthz"
    matcher = "200"
  }
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port             = 80
  protocol         = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      status_code  = "404"
      message_body = "{\"error\":{\"code\":\"NOT_FOUND\",\"message\":\"Not found\"}}"
    }
  }
}

resource "aws_lb_listener_rule" "qa" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main["qa"].arn
  }
  condition {
    path_pattern { values = ["/v1/assistants/*/ask"] }
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 20
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main["api"].arn
  }
  condition {
    path_pattern { values = ["/v1/*"] }
  }
}

resource "aws_cloudfront_vpc_origin" "main" {
  vpc_origin_endpoint_config {
    name                   = "${local.prefix}-alb"
    arn                    = aws_lb.main.arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"
    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
  depends_on = [aws_lb_listener.main, aws_internet_gateway.main, aws_vpc_security_group_ingress_rule.cloudfront_to_alb]
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.prefix}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa" {
  name    = "${local.prefix}-spa"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/spa-rewrite.js")
}

data "aws_cloudfront_cache_policy" "static" { name = "Managed-CachingOptimized" }
data "aws_cloudfront_cache_policy" "disabled" { name = "Managed-CachingDisabled" }
data "aws_cloudfront_origin_request_policy" "api" { name = "Managed-AllViewerExceptHostHeader" }

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  comment             = "${local.prefix} SPA and API"
  default_root_object = "index.html"
  price_class         = "PriceClass_All" # Includes the Sydney edge location.
  http_version        = "http2and3"
  is_ipv6_enabled     = true

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.main["web"].bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }
  origin {
    origin_id   = "api"
    domain_name = aws_lb.main.dns_name
    vpc_origin_config {
      vpc_origin_id          = aws_cloudfront_vpc_origin.main.id
      origin_keepalive_timeout = 5
      origin_read_timeout      = 60
    }
  }
  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.static.id
    compress               = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }
  ordered_cache_behavior {
    path_pattern           = "/v1/*"
    target_origin_id       = "api"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
    compress               = false # Preserve incremental SSE delivery.
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.main["web"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject"
        Resource = "${aws_s3_bucket.main["web"].arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.main.arn } }
      },
      {
        Effect = "Deny", Principal = "*", Action = "s3:*"
        Resource = [aws_s3_bucket.main["web"].arn, "${aws_s3_bucket.main["web"].arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })
}

# RAGcat's own sign-in page calls the API, which signs in through the Cognito API: no hosted login
# page, callback URLs or domain. The api service creates confirmed accounts itself (see iam.tf).
resource "aws_cognito_user_pool_client" "web" {
  name                          = "${local.prefix}-web"
  user_pool_id                  = var.cognito_pool_id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  access_token_validity         = 1
  id_token_validity             = 1
  refresh_token_validity        = 7
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
}
