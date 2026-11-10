data "google_project" "project" {
  project_id = var.project_id
}

resource "google_service_account" "terraform_ci_sa" {
  account_id   = var.terraform_cicd_sa
  display_name = "Terraform CI/CD Apply Service Account"
  project      = var.project_id
}

resource "google_service_account" "terraform_plan_sa" {
  account_id   = "${var.terraform_cicd_sa}-plan"
  display_name = "Terraform CI/CD Plan (Read-Only) Service Account"
  project      = var.project_id
}

locals {
  ci_apply_roles = [
    "roles/viewer",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/iam.securityAdmin",
    "roles/secretmanager.admin",
    "roles/storage.admin",
    "roles/bigquery.admin",
    "roles/cloudfunctions.admin",
    "roles/run.admin",
    "roles/workflows.admin",
    "roles/cloudscheduler.admin",
    "roles/dataform.admin",
    "roles/monitoring.admin",
    "roles/cloudbuild.builds.editor",
    "roles/logging.logWriter",
  ]

  ci_plan_roles = [
    "roles/viewer",
    "roles/iam.securityReviewer",
    "roles/storage.objectViewer",
    "roles/logging.logWriter",
  ]
}

resource "google_project_iam_member" "terraform_ci_sa_roles" {
  for_each = toset(local.ci_apply_roles)

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.terraform_ci_sa.email}"
}

resource "google_project_iam_member" "terraform_plan_sa_roles" {
  for_each = toset(local.ci_plan_roles)

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.terraform_plan_sa.email}"
}

resource "google_service_account_iam_member" "cloudbuild_impersonation" {
  service_account_id = google_service_account.terraform_ci_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "cloudbuild_plan_impersonation" {
  service_account_id = google_service_account.terraform_plan_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

# Allow the read-only plan SA to read/lock Terraform state in the tfstate bucket
resource "google_storage_bucket_iam_member" "plan_sa_tfstate_access" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.terraform_plan_sa.email}"
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

# Allow the read-only plan SA to upload plan files to the tf-plans bucket
resource "google_storage_bucket_iam_member" "plan_sa_tfplans_access" {
  bucket = google_storage_bucket.tf_plans.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.terraform_plan_sa.email}"
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
      branch = "^main$"
    }
  }

  service_account = google_service_account.terraform_plan_sa.id
  filename        = "cloudbuild.plan.yaml"

  substitutions = {
    _PLAN_BUCKET = google_storage_bucket.tf_plans.name
  }

  depends_on = [
    google_project_iam_member.terraform_plan_sa_roles,
    google_service_account_iam_member.cloudbuild_plan_impersonation,
    google_storage_bucket_iam_member.plan_sa_tfstate_access,
    google_storage_bucket_iam_member.plan_sa_tfplans_access,
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
