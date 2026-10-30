# Two ways CloudFront reaches the ALB:
# - default: an internal ALB through a CloudFront VPC origin, so the ALB has no public address;
# - var.shared_account (no security-group rules can be added): an internet-facing ALB on HTTPS that
#   forwards only requests carrying CloudFront's secret header. Direct requests get the 404 default,
#   so the widget rate limit can still trust CloudFront-Viewer-Address.
locals {
  origin_domain = local.shared ? "${var.student_id}-ragcat-api.${var.shared_account.origin_zone_name}" : null
  site_domain   = local.shared ? "${var.student_id}-ragcat.${var.shared_account.origin_zone_name}" : null
  origin_header = "X-RAGcat-Origin"
}

resource "aws_lb" "main" {
  name               = "${local.prefix}-alb"
  internal           = !local.shared
  load_balancer_type = "application"
  subnets            = local.shared ? local.public_subnets : local.private_subnets
  security_groups    = local.alb_sgs
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

resource "random_password" "origin" {
  count   = local.shared ? 1 : 0
  length  = 40
  special = false
}

resource "aws_acm_certificate" "origin" {
  count             = local.shared ? 1 : 0
  domain_name       = local.origin_domain
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

# The student role has no route53:GetChange, so Terraform can't wait on Route 53 changes. The DNS records are
# created by hand in the cab432.com zone: an A alias for local.origin_domain to the ALB, and (only needed
# for renewal) the ACM validation CNAME. The certificate is already ISSUED; this just waits for that status.
resource "aws_acm_certificate_validation" "origin" {
  count           = local.shared ? 1 : 0
  certificate_arn = aws_acm_certificate.origin[0].arn
}

# The site's own name at CloudFront. Its validation CNAME and the A alias to the distribution are also
# created by hand (ACM console: "Create records in Route 53"); apply waits here until the certificate is ISSUED.
resource "aws_acm_certificate" "site" {
  count             = local.shared ? 1 : 0
  provider          = aws.us_east_1
  domain_name       = local.site_domain
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_acm_certificate_validation" "site" {
  count           = local.shared ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site[0].arn
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = local.shared ? 443 : 80
  protocol          = local.shared ? "HTTPS" : "HTTP"
  certificate_arn   = local.shared ? aws_acm_certificate_validation.origin[0].certificate_arn : null
  ssl_policy        = local.shared ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
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
    path_pattern { values = ["/v1/assistants/*/ask", "/v1/widget/*/ask"] } # owner Test and Website widget
  }
  dynamic "condition" {
    for_each = random_password.origin
    content {
      http_header {
        http_header_name = local.origin_header
        values           = [condition.value.result]
      }
    }
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
  dynamic "condition" {
    for_each = random_password.origin
    content {
      http_header {
        http_header_name = local.origin_header
        values           = [condition.value.result]
      }
    }
  }
}

resource "aws_cloudfront_vpc_origin" "main" {
  count = local.shared ? 0 : 1
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
  aliases             = local.shared ? [local.site_domain] : []

  origin {
    origin_id                = "web"
    domain_name              = data.aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }
  origin {
    origin_id   = "api"
    domain_name = local.shared ? local.origin_domain : aws_lb.main.dns_name
    dynamic "vpc_origin_config" {
      for_each = aws_cloudfront_vpc_origin.main
      content {
        vpc_origin_id            = vpc_origin_config.value.id
        origin_keepalive_timeout = 5
        origin_read_timeout      = 60
      }
    }
    dynamic "custom_origin_config" {
      for_each = random_password.origin
      content {
        http_port                = 80
        https_port               = 443
        origin_protocol_policy   = "https-only"
        origin_ssl_protocols     = ["TLSv1.2"]
        origin_keepalive_timeout = 5
        origin_read_timeout      = 60
      }
    }
    dynamic "custom_header" {
      for_each = random_password.origin
      content {
        name  = local.origin_header
        value = custom_header.value.result
      }
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
    path_pattern             = "/v1/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
    compress                 = false # Preserve incremental SSE delivery.
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    cloudfront_default_certificate = !local.shared
    acm_certificate_arn            = local.shared ? aws_acm_certificate_validation.site[0].certificate_arn : null
    ssl_support_method             = local.shared ? "sni-only" : null
    minimum_protocol_version       = local.shared ? "TLSv1.2_2021" : null
  }
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
