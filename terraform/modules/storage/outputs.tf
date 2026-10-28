output "bucket_name" {
  description = "The name of the raw data bucket"
  value       = google_storage_bucket.raw_bucket.name
}

output "bucket_url" {
  description = "The URL of the raw data bucket"
  value       = google_storage_bucket.raw_bucket.url
}
