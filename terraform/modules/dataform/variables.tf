variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "git_repository_url" {
  description = "The URL of the Git repository"
  type        = string
}

variable "default_branch" {
  description = "The default Git branch for Dataform"
  type        = string
  default     = "main"
}

variable "workflow_sa_email" {
  description = "The service account email of the Cloud Workflows orchestrator"
  type        = string
}

variable "raw_dataset_id" {
  description = "The ID of the raw BigQuery dataset"
  type        = string
}

variable "staging_dataset_id" {
  description = "The ID of the staging BigQuery dataset"
  type        = string
}

variable "marts_dataset_id" {
  description = "The ID of the marts BigQuery dataset"
  type        = string
}

variable "assertions_dataset_id" {
  description = "The ID of the assertions BigQuery dataset"
  type        = string
}

variable "biglake_connection_id" {
  description = "The ID of the BigLake GCS connection"
  type        = string
}
