output "site_url" { value = "https://${local.shared ? local.site_domain : aws_cloudfront_distribution.main.domain_name}" }
output "web_bucket" { value = data.aws_s3_bucket.web.id }
output "cloudfront_distribution_id" { value = aws_cloudfront_distribution.main.id }
output "region" { value = var.region }
output "account_id" { value = local.account_id }
output "student_id" { value = var.student_id }
output "qut_username" { value = var.qut_username }
output "cluster_arn" { value = local.cluster_arn }
output "service_names" { value = { for key, service in aws_ecs_service.main : key => service.name } }
output "ecr_repositories" { value = { for key, repo in aws_ecr_repository.main : key => repo.repository_url } }
output "dashboard_url" { value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}" }

# Route 53 records are created by hand (no route53:GetChange), so they are listed only when the zone ID is set.
locals {
  dns_records = try(var.shared_account.origin_zone_id, null) == null ? [] : [
    { name = local.origin_domain, type = "A", description = "Points the ALB origin name that CloudFront connects to at the load balancer." },
    { name = local.site_domain, type = "A", description = "Points the site's own name at the CloudFront distribution." },
  ]
}

# Used by deploy.py to generate the assessment YAML from actual, applied identifiers.
output "cloud_resources" {
  value = concat(
    [
      { type = "DynamoDB table", arn = aws_dynamodb_table.main.arn, description = "Stores owners, usage, Assistants, Documents, and Passages in one table with GSI1." },
      { type = "S3 Vectors bucket", arn = aws_s3vectors_vector_bucket.main.vector_bucket_arn, description = "Stores the Passage vector index." },
      { type = "S3 Vectors index", arn = aws_s3vectors_index.passages.index_arn, description = "Searches published Passage vectors by Assistant with cosine similarity." },
      { type = "ECS cluster", arn = local.cluster_arn, description = "Runs the api and qa services; may be an existing shared cluster." },
      { type = "Application Load Balancer", arn = aws_lb.main.arn, description = "Routes management and streaming question requests to separate ECS services." },
      { type = "ALB listener", arn = aws_lb_listener.main.arn, description = local.shared ? "Accepts HTTPS from CloudFront on port 443 and forwards only requests carrying its secret origin header." : "Accepts private CloudFront origin HTTP traffic on port 80." },
      { type = "CloudFront distribution", arn = aws_cloudfront_distribution.main.arn, description = "Provides the HTTPS SPA and same-origin API entry point." },
      { type = "CloudFront function", arn = aws_cloudfront_function.spa.arn, description = "Rewrites SPA routes to index.html without masking API failures." },
      { type = "CloudFront origin access control", arn = aws_cloudfront_origin_access_control.web.id, description = "Allows only this distribution to read the private SPA bucket." },
      { type = "Cognito User Pool", arn = "arn:${local.partition}:cognito-idp:${var.region}:${local.account_id}:userpool/${var.cognito_pool_id}", description = "Existing User Pool authenticates owners; Terraform does not change the shared pool." },
      { type = "Cognito App Client", arn = "${var.cognito_pool_id}/${aws_cognito_user_pool_client.web.id}", description = "Dedicated public client for RAGcat's own sign-in page: password and refresh-token sign-in through the API, no client secret." },
      { type = "EventBridge rule", arn = aws_cloudwatch_event_rule.upload.arn, description = "Sends new uploads from the files bucket to the parse queue." },
      { type = "ElastiCache replication group", arn = aws_elasticache_replication_group.main.arn, description = "Shares Assistant configuration, question vectors, and answer caches between runtimes." },
      { type = "ElastiCache subnet group", arn = aws_elasticache_subnet_group.main.name, description = "Keeps Valkey in private subnets." },
      { type = "CloudWatch dashboard", arn = aws_cloudwatch_dashboard.main.dashboard_arn, description = "Displays scaling, request load, cache metrics, queue backlog, and answer latency." },
    ],
    # Shared-account networks, security groups and roles belong to the account, not this project.
    [for vpc in aws_vpc.main : { type = "VPC", arn = vpc.arn, description = "Contains private application and cache subnets and the CloudFront origin." }],
    [for origin in aws_cloudfront_vpc_origin.main : { type = "CloudFront VPC origin", arn = origin.arn, description = "Connects CloudFront privately to the internal ALB." }],
    [for role in aws_iam_role.ecs_execution : { type = "IAM role", arn = role.arn, description = "Allows ECS to pull project images and write runtime logs." }],
    [for cert in aws_acm_certificate.origin : { type = "ACM certificate", arn = cert.arn, description = "Serves HTTPS on the ALB origin name CloudFront connects to." }],
    [for cert in aws_acm_certificate.site : { type = "ACM certificate", arn = cert.arn, description = "Serves HTTPS on the site's own name at CloudFront, which accepts only us-east-1 certificates." }],
    [for record in local.dns_records : { type = "Route 53 record", arn = "${var.shared_account.origin_zone_id}/${record.name}/${record.type}", description = record.description }],
    [{ type = "S3 bucket", arn = data.aws_s3_bucket.files.arn, description = "Stores private uploaded PDFs and rendered page images." }],
    [{ type = "S3 bucket", arn = data.aws_s3_bucket.web.arn, description = "Stores the React SPA and public runtime authentication configuration." }],
    [for repo in aws_ecr_repository.main : { type = "ECR repository", arn = repo.arn, description = "Stores immutable ARM64 container images used by RAGcat runtimes." }],
    [for queue in aws_sqs_queue.main : { type = "SQS queue", arn = queue.arn, description = "Buffers asynchronous parsing or vector reconciliation jobs." }],
    [for queue in aws_sqs_queue.dlq : { type = "SQS dead-letter queue", arn = queue.arn, description = "Retains jobs that exhaust three worker deliveries." }],
    [for worker in aws_lambda_function.main : { type = "Lambda function", arn = worker.arn, description = "Processes one queued PDF parsing or vector reconciliation job." }],
    [for mapping in aws_lambda_event_source_mapping.main : { type = "Lambda event source mapping", arn = mapping.uuid, description = "Invokes a worker for SQS messages with bounded concurrency and batch size one." }],
    [for service in aws_ecs_service.main : { type = "ECS service", arn = service.id, description = "Runs an independently scalable API or question-answering service." }],
    [for task in aws_ecs_task_definition.main : { type = "ECS task definition", arn = task.arn, description = "Defines an ARM64 stateless application container pinned to an ECR digest." }],
    [for group in aws_lb_target_group.main : { type = "ALB target group", arn = group.arn, description = "Distributes requests over healthy application tasks." }],
    [for rule in [aws_lb_listener_rule.api, aws_lb_listener_rule.qa] : { type = "ALB listener rule", arn = rule.arn, description = "Selects the application service by request path." }],
    [for target in aws_appautoscaling_target.main : { type = "Application Auto Scaling target", arn = target.resource_id, description = "Bounds the ECS service minimum and maximum task counts." }],
    [for policy in aws_appautoscaling_policy.main : { type = "Application Auto Scaling policy", arn = policy.arn, description = "Changes ECS task count in response to ALB requests per target." }],
    [for group in data.aws_cloudwatch_log_group.runtime : { type = "CloudWatch log group", arn = group.arn, description = "Collects runtime logs." }],
    [for alarm in merge(aws_cloudwatch_metric_alarm.dlq, { for key, alarm in aws_cloudwatch_metric_alarm.lambda_errors : "lambda-${key}" => alarm }, { for key, alarm in aws_cloudwatch_metric_alarm.unhealthy : "alb-${key}" => alarm }) : { type = "CloudWatch alarm", arn = alarm.arn, description = "Detects worker errors, dead-letter jobs, or unhealthy application targets." }],
    [for role in aws_iam_role.runtime : { type = "IAM role", arn = role.arn, description = "Grants a project runtime access to its required data and model resources." }],
    [for sg in concat(aws_security_group.alb, aws_security_group.runtime, aws_security_group.cache) : { type = "Security group", arn = sg.arn, description = "Restricts traffic between CloudFront, the ALB, application runtimes, and cache." }],
    [for subnet in concat(aws_subnet.public, aws_subnet.private) : { type = "Subnet", arn = subnet.arn, description = "Provides a public egress or private application network segment." }],
    [for nat in aws_nat_gateway.main : { type = "NAT gateway", arn = nat.id, description = "Provides outbound AWS API access for private ECS and Lambda runtimes." }],
    [for gateway in aws_internet_gateway.main : { type = "Internet gateway", arn = gateway.id, description = "Provides the VPC internet attachment required for CloudFront VPC origins and NAT egress." }],
    [for address in aws_eip.nat : { type = "Elastic IP", arn = address.id, description = "Provides the NAT gateway public egress address." }],
    [for table in concat(aws_route_table.public, aws_route_table.private) : { type = "Route table", arn = table.arn, description = "Routes public traffic through the internet gateway and private egress through NAT." }],
    [for model in local.bedrock_models : { type = "Bedrock foundation model", arn = model, description = "Provides embedding, contextual generation, answers, or figure descriptions." }],
  )
}
