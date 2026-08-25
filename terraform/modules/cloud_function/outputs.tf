output "function_uri" {
  description = "The URI of the Cloud Function"
  value       = google_cloudfunctions2_function.fetch_weather.service_config[0].uri
}

output "function_name" {
  description = "The name of the Cloud Function"
  value       = google_cloudfunctions2_function.fetch_weather.name
}
