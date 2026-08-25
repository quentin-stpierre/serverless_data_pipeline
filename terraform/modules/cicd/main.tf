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

resource "google_service_account_iam_member" "cloudbuild_impersonation" {
  service_account_id = google_service_account.terraform_ci_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

resource "google_storage_bucket" "tf_plans" {
  name                        = "${var.project_id}-tf-plans"
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 14 # auto-clean stale/abandoned plans after 2 weeks
    }
    action {
      type = "Delete"
    }
  }
}

# --- PR trigger: runs `terraform plan`, reports pass/fail as a GitHub check ---
resource "google_cloudbuild_trigger" "terraform_plan_trigger" {
  name        = var.cloud_build_trigger_name
  description = "Run Terraform Plan on pull requests targeting main"
  project     = var.project_id

  github {
    owner = var.github_owner
    name  = var.github_repo
    pull_request {
      branch          = "^main$"
      comment_control = "COMMENTS_DISABLED"
    }
  }

  service_account = google_service_account.terraform_ci_sa.id
  filename        = "cloudbuild.plan.yaml"

  substitutions = {
    _PLAN_BUCKET = google_storage_bucket.tf_plans.name
  }

  depends_on = [
    google_project_iam_member.terraform_ci_sa_roles,
    google_service_account_iam_member.cloudbuild_impersonation
  ]
}

# --- Push-to-main trigger: runs `terraform apply`, paused for manual approval ---
resource "google_cloudbuild_trigger" "terraform_apply_trigger" {
  name        = "${var.cloud_build_trigger_name}-apply"
  description = "Run Terraform Apply on push to main, gated by manual approval"
  project     = var.project_id

  github {
    owner = var.github_owner
    name  = var.github_repo
    push {
      branch = "^main$"
    }
  }

  service_account = google_service_account.terraform_ci_sa.id
  filename        = "cloudbuild.apply.yaml"

  approval_config {
    approval_required = true
  }

  substitutions = {
    _PLAN_BUCKET = google_storage_bucket.tf_plans.name
  }

  depends_on = [
    google_project_iam_member.terraform_ci_sa_roles,
    google_service_account_iam_member.cloudbuild_impersonation
  ]
}

# Whoever needs to click "Approve"/"Reject" on the apply build needs this role
resource "google_project_iam_member" "terraform_apply_approvers" {
  for_each = toset(var.terraform_apply_approvers) # e.g. ["user:alice@example.com", "group:platform-team@example.com"]

  project = var.project_id
  role    = "roles/cloudbuild.builds.approver"
  member  = each.key
}
