variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "function_uri" {
  description = "The URI of the Cloud Function to invoke"
  type        = string
}

variable "function_name" {
  description = "The name of the Cloud Function to invoke"
  type        = string
}

variable "workflow_name" {
  description = "The name of the Cloud Workflow"
  type        = string
}

variable "workflow_sa_name" {
  description = "The name of the workflow service account."
  type        = string
}

variable "dataform_repo_name" {
  description = "The name of the Dataform repository to invoke"
  type        = string
}

variable "dataform_runner_sa_email" {
  description = "The service account email used for Dataform invocations"
  type        = string
}
