resource "aws_sqs_queue" "orders_queue" {
  name                      = "orders-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "orders"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "orders_dlq" {
  name                      = "orders-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "orders"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "orders" {
  name              = "/aws/service/orders"
  retention_in_days = 14
}

resource "aws_iam_role" "orders_exec" {
  name = "orders-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "users_queue" {
  name                      = "users-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "users"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "users_dlq" {
  name                      = "users-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "users"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "users" {
  name              = "/aws/service/users"
  retention_in_days = 14
}

resource "aws_iam_role" "users_exec" {
  name = "users-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "payments_queue" {
  name                      = "payments-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "payments"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "payments_dlq" {
  name                      = "payments-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "payments"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "payments" {
  name              = "/aws/service/payments"
  retention_in_days = 14
}

resource "aws_iam_role" "payments_exec" {
  name = "payments-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "inventory_queue" {
  name                      = "inventory-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "inventory"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "inventory_dlq" {
  name                      = "inventory-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "inventory"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "inventory" {
  name              = "/aws/service/inventory"
  retention_in_days = 14
}

resource "aws_iam_role" "inventory_exec" {
  name = "inventory-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "shipping_queue" {
  name                      = "shipping-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "shipping"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "shipping_dlq" {
  name                      = "shipping-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "shipping"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "shipping" {
  name              = "/aws/service/shipping"
  retention_in_days = 14
}

resource "aws_iam_role" "shipping_exec" {
  name = "shipping-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "notifications_queue" {
  name                      = "notifications-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "notifications"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "notifications-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "notifications"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "notifications" {
  name              = "/aws/service/notifications"
  retention_in_days = 14
}

resource "aws_iam_role" "notifications_exec" {
  name = "notifications-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "audit_queue" {
  name                      = "audit-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "audit"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "audit_dlq" {
  name                      = "audit-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "audit"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "audit" {
  name              = "/aws/service/audit"
  retention_in_days = 14
}

resource "aws_iam_role" "audit_exec" {
  name = "audit-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "search_queue" {
  name                      = "search-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "search"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "search_dlq" {
  name                      = "search-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "search"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "search" {
  name              = "/aws/service/search"
  retention_in_days = 14
}

resource "aws_iam_role" "search_exec" {
  name = "search-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "reporting_queue" {
  name                      = "reporting-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "reporting"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "reporting_dlq" {
  name                      = "reporting-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "reporting"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "reporting" {
  name              = "/aws/service/reporting"
  retention_in_days = 14
}

resource "aws_iam_role" "reporting_exec" {
  name = "reporting-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "billing_queue" {
  name                      = "billing-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "billing"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "billing_dlq" {
  name                      = "billing-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "billing"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "billing" {
  name              = "/aws/service/billing"
  retention_in_days = 14
}

resource "aws_iam_role" "billing_exec" {
  name = "billing-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "catalog_queue" {
  name                      = "catalog-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "catalog"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "catalog_dlq" {
  name                      = "catalog-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "catalog"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "catalog" {
  name              = "/aws/service/catalog"
  retention_in_days = 14
}

resource "aws_iam_role" "catalog_exec" {
  name = "catalog-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "pricing_queue" {
  name                      = "pricing-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "pricing"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "pricing_dlq" {
  name                      = "pricing-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "pricing"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "pricing" {
  name              = "/aws/service/pricing"
  retention_in_days = 14
}

resource "aws_iam_role" "pricing_exec" {
  name = "pricing-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "fulfillment_queue" {
  name                      = "fulfillment-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "fulfillment"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "fulfillment_dlq" {
  name                      = "fulfillment-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "fulfillment"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "fulfillment" {
  name              = "/aws/service/fulfillment"
  retention_in_days = 14
}

resource "aws_iam_role" "fulfillment_exec" {
  name = "fulfillment-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "returns_queue" {
  name                      = "returns-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "returns"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "returns_dlq" {
  name                      = "returns-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "returns"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "returns" {
  name              = "/aws/service/returns"
  retention_in_days = 14
}

resource "aws_iam_role" "returns_exec" {
  name = "returns-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_sqs_queue" "support_queue" {
  name                      = "support-queue"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "support"
    Owner   = "backend-team"
  }
}

resource "aws_sqs_queue" "support_dlq" {
  name                      = "support-dlq"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 30

  tags = {
    Service = "support"
    Owner   = "backend-team"
  }
}

resource "aws_cloudwatch_log_group" "support" {
  name              = "/aws/service/support"
  retention_in_days = 14
}

resource "aws_iam_role" "support_exec" {
  name = "support-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

