terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/upload-function"
  retention_in_days = 14
}

# Lambda Function
resource "aws_lambda_function" "upload_processor" {
  filename         = "lambda/upload-function.zip"
  function_name    = "upload-function"
  role            = "arn:aws:iam::961624804946:role/adm-role"
  handler         = "upload-function.lambda_handler"
  runtime         = "python3.11"
  timeout         = 900  # 15 minutos
  memory_size     = 2048 # 2GB

  source_code_hash = filebase64sha256("upload-lambda/src/main/upload-lambda.zip")

  layers = [
    var.ffmpeg_layer_arn
  ]

  environment {
    variables = {
      BUCKET   = "upload-bucket-11soat"
      TABLE    = "upload"
      FFMPEG_PATH         = "/opt/bin/ffmpeg"
      OPENCV_CACHE_DIR    = "/tmp"
      AWS_REGION          = var.aws_region
      ENVIRONMENT         = var.environment
      LOG_LEVEL           = "INFO"
      MAX_FILE_SIZE_MB    = "500"
      ALLOWED_EXTENSIONS  = "mp4,avi,mov,mkv,jpg,jpeg,png,gif,webp"
    }
  }

  ephemeral_storage {
    size = 2048 # 2GB de storage temporário
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_log_group
  ]
}