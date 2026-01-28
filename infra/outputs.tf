output "lambda_function_name" {
  description = "Nome da função Lambda"
  value       = aws_lambda_function.upload_processor.function_name
}

output "lambda_function_arn" {
  description = "ARN da função Lambda"
  value       = aws_lambda_function.upload_processor.arn
}

output "ffmpeg_layer_arn" {
  description = "ARN da layer do FFmpeg"
  value       = var.ffmpeg_layer_arn
}