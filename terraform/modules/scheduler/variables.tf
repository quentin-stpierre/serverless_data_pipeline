variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "workflow_name" {
  description = "The name of the Cloud Workflow to trigger"
  type        = string
}

variable "workflow_trigger_name" {
  description = "The name of the Cloud Workflow trigger (Cloud Schedule trigger)."
  type        = string
}

variable "scheduler_sa_name" {
  description = "The name of the Cloud Scheduler service account."
  type        = string
}
