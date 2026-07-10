variable "project_name" {
  description = "The name of the GCP project"
  type        = string
}

variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "billing_account" {
  description = "The billing account ID to associate with the project"
  type        = string
}

variable "org_id" {
  description = "The organization ID where the project will be created"
  type        = string
}

variable "folder_id" {
  description = "The folder ID where the project will be created"
  type        = string
}

variable "dataset_id" {
  description = "The ID of the BigQuery dataset."
  type        = string
}

variable "table_id" {
  description = "The ID of the BigQuery table."
  type        = string
}

variable "alert_email_address" {
  description = "The email address to send alert notifications to"
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
