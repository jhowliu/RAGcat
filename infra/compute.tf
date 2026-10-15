resource "aws_ecr_repository" "main" {
  for_each             = toset(["service", "worker"])
  name                 = "${local.prefix}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_ecr_repository_policy" "worker" {
  repository = aws_ecr_repository.main["worker"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid = "LambdaImageRetrieval", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }
      Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = { ArnLike = { "aws:SourceArn" = "arn:${local.partition}:lambda:${var.region}:${local.account_id}:function:${local.prefix}-*" } }
    }]
  })
}

data "aws_ecr_image" "main" {
  for_each        = var.deploy_workloads ? aws_ecr_repository.main : {}
  repository_name = each.value.name
  image_tag       = var.image_tag
}

resource "aws_cloudwatch_log_group" "runtime" {
  for_each          = local.runtimes
  name              = contains(["ingest", "embed"], each.key) ? "/aws/lambda/${local.prefix}-${each.key}" : "/${local.prefix}/${each.key}"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "main" {
  count = var.existing_cluster_arn == null ? 1 : 0
  name  = "${local.prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  cluster_arn  = var.existing_cluster_arn == null ? aws_ecs_cluster.main[0].arn : var.existing_cluster_arn
  cluster_name = element(split("/", local.cluster_arn), length(split("/", local.cluster_arn)) - 1)
  environment = {
    AWS_REGION            = var.region
    RAGCAT_TABLE          = aws_dynamodb_table.main.name
    RAGCAT_STORAGE        = "s3"
    RAGCAT_BUCKET         = aws_s3_bucket.main["files"].id
    RAGCAT_QUEUE          = "sqs"
    RAGCAT_PARSE_QUEUE_URL = aws_sqs_queue.main["parse"].url
    RAGCAT_EMBED_QUEUE_URL = aws_sqs_queue.main["embed"].url
    RAGCAT_VECTORS        = "s3vectors"
    RAGCAT_VECTOR_BUCKET  = aws_s3vectors_vector_bucket.main.vector_bucket_name
    RAGCAT_VECTOR_INDEX   = aws_s3vectors_index.passages.index_name
    RAGCAT_MODELS         = "bedrock"
    RAGCAT_EMBED_PROVIDER = "bedrock"
    RAGCAT_LLM_PROVIDER   = "bedrock"
    RAGCAT_VISION_PROVIDER = "bedrock"
    RAGCAT_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
    RAGCAT_EMBED_DIMS     = tostring(var.embed_dimensions)
    RAGCAT_LLM_MODEL_ID   = var.llm_model_id
    RAGCAT_VISION_MODEL_ID = var.vision_model_id
    RAGCAT_CONTEXTUAL    = "on"
    RAGCAT_CACHE         = "valkey"
    RAGCAT_CACHE_URL     = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
    RAGCAT_AUTH          = "cognito"
    # The built Website widget page the api fills in per Assistant (docs/api-design.md §7).
    RAGCAT_WIDGET_TEMPLATE_URL = "https://${aws_cloudfront_distribution.main.domain_name}/widget.html"
    COGNITO_USER_POOL_ID = var.cognito_pool_id
    COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
    RAGCAT_DATA_DIR      = "/tmp/ragcat"
  }
}

resource "aws_ecs_task_definition" "main" {
  for_each                 = var.deploy_workloads ? local.services : {}
  family                   = "${local.prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.runtime[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name      = each.key
    image     = "${aws_ecr_repository.main["service"].repository_url}@${data.aws_ecr_image.main["service"].image_digest}"
    essential = true
    command   = ["uvicorn", "ragcat.apps.${each.key}:app"]
    portMappings = [{ containerPort = 8080, hostPort = 8080, protocol = "tcp" }]
    environment  = [for name, value in local.environment : { name = name, value = value }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.runtime[each.key].name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_ecs_service" "main" {
  for_each                           = var.deploy_workloads ? local.services : {}
  name                               = "${local.prefix}-${each.key}"
  cluster                            = local.cluster_arn
  task_definition                    = aws_ecs_task_definition.main[each.key].arn
  launch_type                        = "FARGATE"
  desired_count                      = 1
  health_check_grace_period_seconds   = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  wait_for_steady_state               = true
  enable_ecs_managed_tags             = true
  propagate_tags                     = "SERVICE"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = local.private_subnets
    security_groups  = [aws_security_group.runtime.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.main[each.key].arn
    container_name   = each.key
    container_port   = 8080
  }
  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.main, aws_lb_listener_rule.api, aws_lb_listener_rule.qa, aws_vpc_security_group_egress_rule.alb_runtime, aws_vpc_security_group_ingress_rule.alb_to_runtime, aws_vpc_security_group_egress_rule.runtime_outbound, aws_vpc_security_group_ingress_rule.runtime_to_cache, aws_iam_role_policy.runtime, aws_iam_role_policy.ecs_execution, aws_route.outbound, aws_route_table_association.private]
}

resource "aws_appautoscaling_target" "main" {
  for_each           = aws_ecs_service.main
  min_capacity       = 1
  max_capacity       = local.services[each.key].max
  resource_id        = "service/${local.cluster_name}/${each.value.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "main" {
  for_each           = aws_appautoscaling_target.main
  name               = "${local.prefix}-${each.key}-requests"
  policy_type        = "TargetTrackingScaling"
  resource_id        = each.value.resource_id
  scalable_dimension = each.value.scalable_dimension
  service_namespace  = each.value.service_namespace
  target_tracking_scaling_policy_configuration {
    target_value       = local.services[each.key].requests
    scale_out_cooldown = 60
    scale_in_cooldown  = 180
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.main[each.key].arn_suffix}"
    }
  }
}

resource "aws_lambda_function" "main" {
  for_each      = var.deploy_workloads ? local.workers : {}
  function_name = "${local.prefix}-${each.key}"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.main["worker"].repository_url}@${data.aws_ecr_image.main["worker"].image_digest}"
  architectures = ["arm64"]
  role          = aws_iam_role.runtime[each.key].arn
  timeout       = 900
  memory_size   = each.value.memory
  # Keep reserved concurrency unset: the shared account may have insufficient reservable capacity.
  image_config { command = ["ragcat.apps.worker.${each.key}"] }
  ephemeral_storage { size = 1024 }
  environment { variables = local.environment }
  vpc_config {
    subnet_ids         = local.private_subnets
    security_group_ids = [aws_security_group.runtime.id]
  }
  depends_on = [aws_iam_role_policy.runtime, aws_iam_role_policy_attachment.lambda_network, aws_ecr_repository_policy.worker, aws_vpc_security_group_egress_rule.runtime_outbound, aws_vpc_security_group_ingress_rule.runtime_to_cache, aws_route.outbound, aws_route_table_association.private]
}

resource "aws_lambda_event_source_mapping" "main" {
  for_each         = aws_lambda_function.main
  event_source_arn = aws_sqs_queue.main[local.workers[each.key].queue].arn
  function_name    = each.value.arn
  batch_size       = 1
  scaling_config { maximum_concurrency = local.workers[each.key].concurrency }
}
