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
