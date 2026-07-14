variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "github_owner" {
  description = "The owner/organization of the GitHub repository"
  type        = string
}

variable "github_repo" {
  description = "The name of the GitHub repository"
  type        = string
}

variable "terraform_cicd_sa" {
  description = "The terraform CI/CD service account."
  type        = string
}

variable "cloud_build_trigger_name" {
  description = "terraform-plan-on-push"
  type        = string
}
