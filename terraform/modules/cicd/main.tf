data "google_project" "project" {
  project_id = var.project_id
}

resource "google_service_account" "terraform_ci_sa" {
  account_id   = var.terraform_cicd_sa
  display_name = "Terraform CI/CD Service Account"
  project      = var.project_id
}

locals {
  ci_roles = [
    "roles/editor",
    "roles/iam.securityAdmin",
    "roles/secretmanager.admin",
    "roles/storage.admin",
  ]
}

resource "google_project_iam_member" "terraform_ci_sa_roles" {
  for_each = toset(local.ci_roles)

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.terraform_ci_sa.email}"
}

# Grant Cloud Build Service Agent permission to act as the custom Service Account
resource "google_service_account_iam_member" "cloudbuild_impersonation" {
  service_account_id = google_service_account.terraform_ci_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

resource "google_cloudbuild_trigger" "terraform_plan_trigger" {
  name        = var.cloud_build_trigger_name
  description = "Trigger to run Terraform Plan on push to main branch"
  project     = var.project_id

  github {
    owner = var.github_owner
    name  = var.github_repo
    push {
      branch = "^main$"
    }
  }

  service_account = google_service_account.terraform_ci_sa.id

  # Use the cloudbuild.yaml at the root
  filename = "cloudbuild.yaml"

  # Ensure roles are fully bound and impersonation is active before trigger is created/run
  depends_on = [
    google_project_iam_member.terraform_ci_sa_roles,
    google_service_account_iam_member.cloudbuild_impersonation
  ]
}
