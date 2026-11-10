variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
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
  description = "terraform-plan-on-pr"
  type        = string
}

variable "terraform_apply_approvers" {
  description = "The list of principals that are allowed to approve the terraform apply."
  type        = list(string)
}
