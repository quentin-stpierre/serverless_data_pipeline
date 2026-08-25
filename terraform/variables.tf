
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
variable "workflow_trigger_name" {
  description = "The name of the Cloud Workflow trigger (Cloud Schedule trigger)."
  type        = string
}
variable "scheduler_sa_name" {
  description = "The name of the Cloud Scheduler service account."
  type        = string
}

### WORKFLOWS ###
variable "workflow_sa_name" {
  description = "The name of the workflow service account."
  type        = string
}
variable "weather_workflow_name" {
  description = "The name of the workflow that triggers the weather processing task."
  type        = string
}

### CLOUD FUNCTION
variable "cloud_function_sa_name" {
  description = "The name of the cloud function service account."
  type        = string
}

variable "cloud_function_name" {
  description = "The name of the cloud function processing weather data."
  type        = string
}

### PUBSUB ###
variable "topic_name" {
  description = "The name of the PubSub topic"
  type        = string
}
variable "bq_subscription_name" {
  description = "The name of BigQuery's PubSub subscription."
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
