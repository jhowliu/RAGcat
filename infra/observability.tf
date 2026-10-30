# The shared account's role is denied logs:PutMetricFilter, so there are no log metric filters. The cache and latency
# widgets below stay empty; read the `answer_completed` lines in the qa log group with Logs Insights instead.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = aws_sqs_queue.dlq
  alarm_name          = "${local.prefix}-${each.key}-dlq"
  alarm_description   = "A worker exhausted its retries; inspect the DLQ and corresponding runtime logs."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each            = aws_lambda_function.main
  alarm_name          = "${local.prefix}-${each.key}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "unhealthy" {
  for_each            = aws_lb_target_group.main
  alarm_name          = "${local.prefix}-${each.key}-unhealthy"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix, TargetGroup = each.value.arn_suffix }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.prefix}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title   = "ECS CPU utilisation", region = var.region, period = 60, stat = "Average"
          metrics = [for name in keys(local.services) : ["AWS/ECS", "CPUUtilization", "ClusterName", local.cluster_name, "ServiceName", "${local.prefix}-${name}"]]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title   = "Running tasks (requires cluster Container Insights)", region = var.region, period = 60, stat = "Average"
          metrics = [for name in keys(local.services) : ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", local.cluster_name, "ServiceName", "${local.prefix}-${name}"]]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title   = "ALB requests per target", region = var.region, period = 60, stat = "Sum"
          metrics = [for group in aws_lb_target_group.main : ["AWS/ApplicationELB", "RequestCountPerTarget", "LoadBalancer", aws_lb.main.arn_suffix, "TargetGroup", group.arn_suffix]]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title   = "Answer cache hits and misses", region = var.region, period = 60, stat = "Sum"
          metrics = [["RAGcat/${local.prefix}", "CacheHits"], ["RAGcat/${local.prefix}", "CacheMisses"]]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 12, height = 6
        properties = {
          title   = "Asynchronous queue backlog", region = var.region, period = 60, stat = "Maximum"
          metrics = [for queue in aws_sqs_queue.main : ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", queue.name]]
        }
      },
      {
        type = "metric", x = 12, y = 12, width = 12, height = 6
        properties = {
          title   = "Answer latency", region = var.region, period = 60, stat = "Average"
          metrics = [["RAGcat/${local.prefix}", "AnswerLatency"]]
        }
      },
    ]
  })
}
