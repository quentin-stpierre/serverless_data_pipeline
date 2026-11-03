output "repository_name" {
  description = "The name of the Dataform repository"
  value       = google_dataform_repository.flights_dataform.name
}

output "repository_id" {
  description = "The ID of the Dataform repository"
  value       = google_dataform_repository.flights_dataform.id
}
