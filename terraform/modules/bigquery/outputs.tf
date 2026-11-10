output "dataset_id" {
  description = "The ID of the raw BigQuery dataset"
  value       = google_bigquery_dataset.dataset.dataset_id
}

output "staging_dataset_id" {
  description = "The ID of the staging BigQuery dataset"
  value       = google_bigquery_dataset.staging.dataset_id
}

output "marts_dataset_id" {
  description = "The ID of the marts BigQuery dataset"
  value       = google_bigquery_dataset.marts.dataset_id
}

output "assertions_dataset_id" {
  description = "The ID of the assertions BigQuery dataset"
  value       = google_bigquery_dataset.assertions.dataset_id
}

output "biglake_connection_id" {
  description = "The connection ID of the BigLake GCS connection"
  value       = google_bigquery_connection.biglake_connection.connection_id
}

output "table_id" {
  description = "The ID of the BigQuery table"
  value       = google_bigquery_table.table.table_id
}
