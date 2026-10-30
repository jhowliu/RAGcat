locals {
  table_resources = [aws_dynamodb_table.main.arn, "${aws_dynamodb_table.main.arn}/index/*"]
  # A restricted account's shared roles replace the per-runtime roles below (their grants are the
  # account's, not this file's).
  ecs_execution_role_arn = local.shared ? var.shared_account.ecs_execution_role_arn : aws_iam_role.ecs_execution[0].arn
  runtime_role_arns = {
    for name in local.runtimes : name => local.shared ? (contains(["api", "qa"], name) ? var.shared_account.ecs_task_role_arn : var.shared_account.lambda_role_arn) : aws_iam_role.runtime[name].arn
  }
  bedrock_models = distinct([
    "arn:${local.partition}:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0",
    "arn:${local.partition}:bedrock:${var.region}::foundation-model/${var.llm_model_id}",
    "arn:${local.partition}:bedrock:${var.region}::foundation-model/${var.vision_model_id}",
  ])
  runtime_permissions = {
    api = [
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${data.aws_s3_bucket.files.arn}/uploads/*"] },
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${data.aws_s3_bucket.files.arn}/pages/*"] },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.main["embed"].arn] },
      # Sign-up creates a confirmed account with a verified email and sends no email (create, set the
      # password, remove it if the password is rejected); sign-in finishes an account left unconfirmed.
      {
        Effect   = "Allow"
        Action   = ["cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminDeleteUser", "cognito-idp:AdminConfirmSignUp", "cognito-idp:AdminUpdateUserAttributes"]
        Resource = ["arn:${local.partition}:cognito-idp:${var.region}:${local.account_id}:userpool/${var.cognito_pool_id}"]
      },
    ]
    qa = [
      { Effect = "Allow", Action = ["s3vectors:QueryVectors", "s3vectors:GetVectors"], Resource = [aws_s3vectors_index.passages.index_arn] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = local.bedrock_models },
    ]
    ingest = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${data.aws_s3_bucket.files.arn}/uploads/*"] },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${data.aws_s3_bucket.files.arn}/pages/*"] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["arn:${local.partition}:bedrock:${var.region}::foundation-model/${var.vision_model_id}"] },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.main["parse"].arn] },
    ]
    embed = [
      { Effect = "Allow", Action = ["s3vectors:PutVectors", "s3vectors:DeleteVectors"], Resource = [aws_s3vectors_index.passages.index_arn] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.bedrock_models },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.main["embed"].arn] },
      { Effect = "Allow", Action = ["s3:DeleteObject"], Resource = ["${data.aws_s3_bucket.files.arn}/uploads/*", "${data.aws_s3_bucket.files.arn}/pages/*"] },
      {
        Effect    = "Allow", Action = ["s3:ListBucket"], Resource = [data.aws_s3_bucket.files.arn]
        Condition = { StringLike = { "s3:prefix" = "pages/*" } }
      },
    ]
  }
}

resource "aws_iam_role" "runtime" {
  for_each = local.shared ? toset([]) : local.runtimes
  name     = "${local.prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRole"
      Principal = { Service = contains(["api", "qa"], each.key) ? "ecs-tasks.amazonaws.com" : "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "runtime" {
  for_each = aws_iam_role.runtime
  name     = "${local.prefix}-${each.key}-data"
  role     = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem", "dynamodb:TransactWriteItems"]
        Resource = local.table_resources
      },
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${data.aws_cloudwatch_log_group.runtime[each.key].arn}:*"]
      },
    ], local.runtime_permissions[each.key])
  })
}

resource "aws_iam_role_policy_attachment" "lambda_network" {
  for_each   = local.shared ? {} : local.workers
  role       = aws_iam_role.runtime[each.key].name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role" "ecs_execution" {
  count = local.shared ? 0 : 1
  name  = "${local.prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "ecs_execution" {
  count = local.shared ? 0 : 1
  name  = "${local.prefix}-image-pull"
  role  = aws_iam_role.ecs_execution[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = [for repo in aws_ecr_repository.main : repo.arn] },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = [for name in ["api", "qa"] : "${data.aws_cloudwatch_log_group.runtime[name].arn}:*"] },
    ]
  })
}
