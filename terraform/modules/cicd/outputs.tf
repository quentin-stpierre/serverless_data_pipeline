output "trigger_id" {
  description = "The ID of the Cloud Build Trigger"
  value       = google_cloudbuild_trigger.terraform_plan_trigger.id
}

output "service_account_email" {
  description = "The email of the Cloud Build execution Service Account"
  value       = google_service_account.terraform_ci_sa.email
}
