output "function_uri" {
  description = "The URI of the Cloud Function"
  value       = google_cloudfunctions2_function.fetch_flights.service_config[0].uri
}

output "function_name" {
  description = "The name of the Cloud Function"
  value       = google_cloudfunctions2_function.fetch_flights.name
}

output "function_sa_email" {
  description = "The service account email of the Cloud Function"
  value       = google_service_account.function_sa.email
}

output "socs_cookie_secret_id" {
  description = "The Secret Manager secret ID for the SOCS consent cookie"
  value       = google_secret_manager_secret.socs_consent_cookie.secret_id
}
