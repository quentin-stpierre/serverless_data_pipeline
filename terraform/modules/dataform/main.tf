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

# Dataform managed repository linked to the monorepo GitHub repository
resource "google_dataform_repository" "flights_dataform" {
  project = var.project_id
  region  = var.region
  name    = "flights-dataform-repo"

  git_remote_settings {
    url                                 = var.git_repository_url
    default_branch                      = var.default_branch
    authentication_token_secret_version = "${google_secret_manager_secret.github_token.id}/versions/latest"
  }

  workspace_compilation_overrides {
    default_database = var.project_id
  }

  depends_on = [
    google_secret_manager_secret_iam_member.dataform_secret_accessor
  ]
}
