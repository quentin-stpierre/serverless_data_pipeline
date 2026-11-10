output "scheduler_job_names" {
  description = "The names of the Cloud Scheduler jobs"
  value       = { for k, v in google_cloud_scheduler_job.flight_pipeline_triggers : k => v.name }
}

output "scheduler_job_ids" {
  description = "The IDs of the Cloud Scheduler jobs"
  value       = { for k, v in google_cloud_scheduler_job.flight_pipeline_triggers : k => v.id }
}
