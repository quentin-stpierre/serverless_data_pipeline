output "workflow_name" {
  description = "The name of the Cloud Workflow"
  value       = google_workflows_workflow.weather_workflow.name
}

output "workflow_id" {
  description = "The ID of the Cloud Workflow"
  value       = google_workflows_workflow.weather_workflow.id
}
