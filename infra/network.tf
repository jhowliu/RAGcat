locals {
  create_network = var.existing_network == null
  vpc_id         = local.create_network ? aws_vpc.main[0].id : var.existing_network.vpc_id
  public_subnets = local.create_network ? aws_subnet.public[*].id : var.existing_network.public_subnet_ids
  private_subnets = local.create_network ? aws_subnet.private[*].id : var.existing_network.private_subnet_ids
}

resource "aws_vpc" "main" {
  count                = local.create_network ? 1 : 0
  cidr_block           = "10.43.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${local.prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  count  = local.create_network ? 1 : 0
  vpc_id = local.vpc_id
  tags   = { Name = "${local.prefix}-igw" }
}

resource "aws_subnet" "public" {
  count             = local.create_network ? 2 : 0
  vpc_id            = local.vpc_id
  cidr_block        = cidrsubnet("10.43.0.0/16", 8, count.index)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${local.prefix}-public-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count             = local.create_network ? 2 : 0
  vpc_id            = local.vpc_id
  cidr_block        = cidrsubnet("10.43.0.0/16", 8, 10 + count.index)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${local.prefix}-private-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  count  = local.create_network ? 1 : 0
  vpc_id = local.vpc_id
  tags   = { Name = "${local.prefix}-public" }
}

resource "aws_route" "internet" {
  count                  = local.create_network ? 1 : 0
  route_table_id         = aws_route_table.public[0].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main[0].id
}

resource "aws_route_table_association" "public" {
  count          = local.create_network ? 2 : 0
  subnet_id      = local.public_subnets[count.index]
  route_table_id = aws_route_table.public[0].id
}

# One NAT for the assessment keeps outbound access simple. It is a single-AZ egress dependency.
resource "aws_eip" "nat" {
  count  = local.create_network ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${local.prefix}-nat" }
}

resource "aws_nat_gateway" "main" {
  count         = local.create_network ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = local.public_subnets[0]
  depends_on    = [aws_internet_gateway.main, aws_route.internet, aws_route_table_association.public]
  tags          = { Name = "${local.prefix}-nat" }
}

resource "aws_route_table" "private" {
  count  = local.create_network ? 1 : 0
  vpc_id = local.vpc_id
  tags   = { Name = "${local.prefix}-private" }
}

resource "aws_route" "outbound" {
  count                  = local.create_network ? 1 : 0
  route_table_id         = aws_route_table.private[0].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}

resource "aws_route_table_association" "private" {
  count          = local.create_network ? 2 : 0
  subnet_id      = local.private_subnets[count.index]
  route_table_id = aws_route_table.private[0].id
}

data "aws_ec2_managed_prefix_list" "cloudfront" { name = "com.amazonaws.global.cloudfront.origin-facing" }

resource "aws_security_group" "alb" {
  name        = "${local.prefix}-alb"
  description = "CloudFront origin traffic only"
  vpc_id      = local.vpc_id
  tags = { Name = "${local.prefix}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "cloudfront_to_alb" {
  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_security_group" "runtime" {
  name        = "${local.prefix}-runtime"
  description = "ECS and Lambda; API ingress only from the ALB"
  vpc_id      = local.vpc_id
  tags = { Name = "${local.prefix}-runtime" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_to_runtime" {
  security_group_id            = aws_security_group.runtime.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8080
  to_port                      = 8080
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "runtime_outbound" {
  security_group_id = aws_security_group.runtime.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "alb_runtime" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.runtime.id
  from_port                    = 8080
  to_port                      = 8080
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "cache" {
  name        = "${local.prefix}-cache"
  description = "TLS Valkey access from RAGcat runtimes only"
  vpc_id      = local.vpc_id
  tags = { Name = "${local.prefix}-cache" }
}

resource "aws_vpc_security_group_ingress_rule" "runtime_to_cache" {
  security_group_id            = aws_security_group.cache.id
  referenced_security_group_id = aws_security_group.runtime.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}
