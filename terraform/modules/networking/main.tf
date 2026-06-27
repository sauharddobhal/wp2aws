# VPC with a standard 3-tier layout, repeated across `az_count` availability zones:
#   - public subnets    (ALB, NAT gateways)
#   - private-app subnets   (Auto Scaling Group, EFS mount targets)
#   - private-data subnets  (Aurora, ElastiCache)
#
# Data tier is kept in its own subnet tier rather than sharing with the app tier so a
# tighter security group / NACL boundary can be drawn around the database and cache,
# the app tier should never need a route to anything except those two specific
# services, not a flat "private subnet" that also holds other things.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-igw"
  }
}

# --- Public subnets (ALB, NAT) ---

resource "aws_subnet" "public" {
  for_each                = { for idx, az in local.azs : az => idx }
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name_prefix}-public-${each.key}"
    Tier = "public"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${var.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# --- NAT gateways ---
# `single_nat_gateway = true` uses one shared NAT for all private subnets (cheaper, a
# single point of failure for outbound internet access). `false` puts one NAT per AZ
# (higher availability, ~3x the NAT cost). Default false; flip to true for a lower-cost
# non-production environment.

resource "aws_eip" "nat" {
  for_each = var.single_nat_gateway ? toset(["shared"]) : toset(local.azs)
  domain   = "vpc"

  tags = {
    Name = "${var.name_prefix}-nat-eip-${each.key}"
  }
}

resource "aws_nat_gateway" "this" {
  for_each      = var.single_nat_gateway ? toset(["shared"]) : toset(local.azs)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = var.single_nat_gateway ? values(aws_subnet.public)[0].id : aws_subnet.public[each.key].id

  tags = {
    Name = "${var.name_prefix}-nat-${each.key}"
  }

  depends_on = [aws_internet_gateway.this]
}

# --- Private app subnets (ASG, EFS) ---

resource "aws_subnet" "private_app" {
  for_each          = { for idx, az in local.azs : az => idx }
  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, each.value + 10)

  tags = {
    Name = "${var.name_prefix}-private-app-${each.key}"
    Tier = "private-app"
  }
}

resource "aws_route_table" "private_app" {
  for_each = { for idx, az in local.azs : az => idx }
  vpc_id   = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.this["shared"].id : aws_nat_gateway.this[each.key].id
  }

  tags = {
    Name = "${var.name_prefix}-private-app-rt-${each.key}"
  }
}

resource "aws_route_table_association" "private_app" {
  for_each       = aws_subnet.private_app
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_app[each.key].id
}

# --- Private data subnets (Aurora, ElastiCache) ---
# No NAT route at all: the data tier has no business reaching the internet outbound.

resource "aws_subnet" "private_data" {
  for_each          = { for idx, az in local.azs : az => idx }
  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, each.value + 20)

  tags = {
    Name = "${var.name_prefix}-private-data-${each.key}"
    Tier = "private-data"
  }
}

resource "aws_route_table" "private_data" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-private-data-rt"
  }
}

resource "aws_route_table_association" "private_data" {
  for_each       = aws_subnet.private_data
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_data.id
}
