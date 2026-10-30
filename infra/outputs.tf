output "site_url" { value = "https://${local.shared ? local.site_domain : aws_cloudfront_distribution.main.domain_name}" }
output "web_bucket" { value = data.aws_s3_bucket.web.id }
output "cloudfront_distribution_id" { value = aws_cloudfront_distribution.main.id }
output "region" { value = var.region }
output "account_id" { value = local.account_id }
output "cluster_arn" { value = local.cluster_arn }
output "service_names" { value = { for key, service in aws_ecs_service.main : key => service.name } }
output "ecr_repositories" { value = { for key, repo in aws_ecr_repository.main : key => repo.repository_url } }
output "dashboard_url" { value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}" }
