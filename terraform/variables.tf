### GENERAL ###
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

### MONITORING ###
variable "alert_email_address" {
  description = "The email address to send alert notifications to"
  type        = string
}

### CI/CD ###
variable "terraform_cicd_sa" {
  description = "The terraform CI/CD service account."
  type        = string
}
variable "cloud_build_trigger_name" {
  description = "terraform-plan-on-pr"
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
variable "terraform_apply_approvers" {
  description = "The list of principals that are allowed to approve the terraform apply."
  type        = list(string)
}

### CLOUD SCHEDULER ###
variable "scheduler_sa_name" {
  description = "The name of the Cloud Scheduler service account."
  type        = string
}

variable "flight_searches" {
  description = "Map of flight search configurations to schedule"
  type = map(object({
    schedule           = string
    origin             = string
    destination        = string
    start_date         = string
    trip_length        = number
    flexibility_window = number
    trip_type          = optional(string, "")
    currency           = optional(string, "EUR")
    seat               = optional(string, "economy")
    adults             = optional(number, 1)
    max_stops          = optional(number, 0)
  }))
}

### WORKFLOWS ###
variable "workflow_sa_name" {
  description = "The name of the workflow service account."
  type        = string
}
variable "flight_workflow_name" {
  description = "The name of the workflow that triggers the flight scraper."
  type        = string
}

### CLOUD FUNCTION ###
variable "cloud_function_sa_name" {
  description = "The name of the scraper cloud function service account."
  type        = string
}

variable "cloud_function_name" {
  description = "The name of the cloud function executing flight scraping."
  type        = string
}

### STORAGE ###
variable "raw_data_bucket_name" {
  description = "The name of the GCS bucket to store raw flight data"
  type        = string
}

### BIGQUERY ###
variable "dataset_id" {
  description = "The ID of the BigQuery dataset."
  type        = string
}
variable "table_id" {
  description = "The ID of the BigQuery table."
  type        = string
}
