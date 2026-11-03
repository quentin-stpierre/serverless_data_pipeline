output "workflow_name" {
  description = "The name of the Cloud Workflow"
  value       = google_workflows_workflow.pipeline_workflow.name
}

output "workflow_id" {
  description = "The ID of the Cloud Workflow"
  value       = google_workflows_workflow.pipeline_workflow.id
}

output "workflow_sa_email" {
  description = "The service account email of the Workflow"
  value       = google_service_account.workflow_sa.email
}
