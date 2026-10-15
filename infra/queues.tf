resource "aws_sqs_queue" "dlq" {
  for_each                  = toset(["parse", "embed"])
  name                      = "${local.prefix}-${each.key}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled    = true
}

resource "aws_sqs_queue" "main" {
  for_each                   = toset(["parse", "embed"])
  name                       = "${local.prefix}-${each.key}"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 5400 # Six times the Lambda 900s timeout.
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled     = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "main" {
  for_each  = aws_sqs_queue.dlq
  queue_url = each.value.url
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main[each.key].arn]
  })
}

resource "aws_cloudwatch_event_rule" "upload" {
  name        = "${local.prefix}-pdf-uploaded"
  description = "Only new PDFs under uploads/ trigger parsing; generated page images do not."
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.main["files"].id] }
      object = { key = [{ prefix = "uploads/" }] }
    }
  })
}

resource "aws_sqs_queue_policy" "parse" {
  queue_url = aws_sqs_queue.main["parse"].url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage"
      Resource  = aws_sqs_queue.main["parse"].arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.upload.arn }, StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_cloudwatch_event_target" "parse" {
  rule       = aws_cloudwatch_event_rule.upload.name
  target_id  = "parse"
  arn        = aws_sqs_queue.main["parse"].arn
  depends_on = [aws_sqs_queue_policy.parse]
}
