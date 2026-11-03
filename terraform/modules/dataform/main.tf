# Generate/retrieve the Dataform service identity
resource "google_project_service_identity" "dataform_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "dataform.googleapis.com"
}

# Secret container for the GitHub Personal Access Token
resource "google_secret_manager_secret" "github_token" {
  project   = var.project_id
  secret_id = "dataform-github-token"

  replication {
    auto {}
  }
}

# Grant Dataform service account access to the GitHub token secret
resource "google_secret_manager_secret_iam_member" "dataform_secret_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.github_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_project_service_identity.dataform_sa.member
}

# Grant Dataform service account BigQuery permissions to run queries and manage tables
resource "google_project_iam_member" "dataform_bigquery_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = google_project_service_identity.dataform_sa.member
}

resource "google_project_iam_member" "dataform_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = google_project_service_identity.dataform_sa.member
}

# Dedicated user-managed service account to execute Dataform SQL workflows
resource "google_service_account" "dataform_runner" {
  account_id   = "flights-dataform-sa"
  display_name = "Flights Dataform Execution Service Account"
  project      = var.project_id
}

# Grant BigQuery permissions to the custom execution service account
resource "google_project_iam_member" "dataform_runner_bigquery_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dataform_runner.email}"
}

resource "google_project_iam_member" "dataform_runner_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dataform_runner.email}"
}

resource "google_project_iam_member" "dataform_runner_bigquery_connection_user" {
  project = var.project_id
  role    = "roles/bigquery.connectionUser"
  member  = "serviceAccount:${google_service_account.dataform_runner.email}"
}

# Allow Dataform Service Agent to generate tokens and act as the execution service account
resource "google_service_account_iam_member" "dataform_sa_token_creator" {
  service_account_id = google_service_account.dataform_runner.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_project_service_identity.dataform_sa.member
}

resource "google_service_account_iam_member" "dataform_sa_user" {
  service_account_id = google_service_account.dataform_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_project_service_identity.dataform_sa.member
}

# Allow Cloud Workflows to pass/act-as this service account when creating workflow invocations
resource "google_service_account_iam_member" "workflow_act_as_dataform_runner" {
  service_account_id = google_service_account.dataform_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.workflow_sa_email}"
}

# Dataform managed repository linked to the monorepo GitHub repository
resource "google_dataform_repository" "flights_dataform" {
  project         = var.project_id
  region          = var.region
  name            = "flights-dataform-repo"
  service_account = google_service_account.dataform_runner.email

  git_remote_settings {
    url                                 = var.git_repository_url
    default_branch                      = var.default_branch
    authentication_token_secret_version = "${google_secret_manager_secret.github_token.id}/versions/latest"
  }

  workspace_compilation_overrides {
    default_database = var.project_id
  }

  depends_on = [
    google_secret_manager_secret_iam_member.dataform_secret_accessor,
    google_service_account_iam_member.dataform_sa_token_creator,
    google_service_account_iam_member.dataform_sa_user
  ]
}
