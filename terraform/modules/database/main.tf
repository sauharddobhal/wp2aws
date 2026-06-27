# Aurora MySQL cluster (one writer, one reader for read scaling) behind RDS Proxy.
#
# RDS Proxy matters more than it might look here: PHP-FPM workers open and close
# connections far more often than a long-lived application server would, and at a few
# hundred req/s peak across several instances, that's enough simultaneous connection
# churn to threaten Aurora's max_connections if the app tier talks to the database
# directly. The proxy pools connections so the app tier can scale out without that
# becoming a database-side problem.

resource "random_password" "master" {
  length  = 24
  special = false # Aurora master password has character restrictions; keep it simple and safe
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${var.name_prefix}-db-credentials"
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
  })
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnet-group"
  subnet_ids = var.private_data_subnet_ids
}

resource "aws_rds_cluster_parameter_group" "this" {
  name        = "${var.name_prefix}-aurora-mysql-params"
  family      = "aurora-mysql8.0"
  description = "Tuned parameter group for the WordPress Aurora MySQL cluster."

  parameter {
    name  = "max_connections"
    value = "2000"
  }
}

resource "aws_rds_cluster" "this" {
  cluster_identifier               = "${var.name_prefix}-aurora"
  engine                           = "aurora-mysql"
  engine_version                   = var.engine_version
  database_name                    = var.database_name
  master_username                  = var.master_username
  master_password                  = random_password.master.result
  db_subnet_group_name              = aws_db_subnet_group.this.name
  vpc_security_group_ids           = [var.aurora_security_group_id]
  db_cluster_parameter_group_name  = aws_rds_cluster_parameter_group.this.name
  storage_encrypted                = true
  backup_retention_period          = var.backup_retention_days
  preferred_backup_window          = "03:00-04:00"
  deletion_protection              = var.deletion_protection
  skip_final_snapshot              = !var.deletion_protection

  tags = {
    Name = "${var.name_prefix}-aurora"
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.name_prefix}-aurora-writer"
  cluster_identifier = aws_rds_cluster.this.id
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
  instance_class     = var.instance_class

  tags = {
    Name = "${var.name_prefix}-aurora-writer"
  }
}

resource "aws_rds_cluster_instance" "reader" {
  count              = var.reader_count
  identifier         = "${var.name_prefix}-aurora-reader-${count.index}"
  cluster_identifier = aws_rds_cluster.this.id
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
  instance_class     = var.instance_class

  tags = {
    Name = "${var.name_prefix}-aurora-reader-${count.index}"
  }
}

# --- RDS Proxy ---

resource "aws_iam_role" "rds_proxy" {
  name = "${var.name_prefix}-rds-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "rds_proxy_secrets_access" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db_credentials.arn]
  }
}

resource "aws_iam_role_policy" "rds_proxy_secrets_access" {
  name   = "${var.name_prefix}-rds-proxy-secrets-access"
  role   = aws_iam_role.rds_proxy.id
  policy = data.aws_iam_policy_document.rds_proxy_secrets_access.json
}

resource "aws_db_proxy" "this" {
  name                   = "${var.name_prefix}-rds-proxy"
  engine_family          = "MYSQL"
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_subnet_ids         = var.private_data_subnet_ids
  vpc_security_group_ids = [var.rds_proxy_security_group_id]
  require_tls            = true

  auth {
    auth_scheme = "SECRETS"
    secret_arn  = aws_secretsmanager_secret.db_credentials.arn
    iam_auth    = "DISABLED"
  }
}

resource "aws_db_proxy_default_target_group" "this" {
  db_proxy_name = aws_db_proxy.this.name

  connection_pool_config {
    max_connections_percent      = 100
    max_idle_connections_percent = 50
  }
}

resource "aws_db_proxy_target" "this" {
  db_proxy_name         = aws_db_proxy.this.name
  target_group_name     = aws_db_proxy_default_target_group.this.name
  db_cluster_identifier = aws_rds_cluster.this.cluster_identifier
}
