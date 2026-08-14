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

variable "pubsub_topic_name" {
  description = "The name of the Pub/Sub topic to publish to"
  type        = string
}

variable "weather_workflow_name" {
  description = "The name of the workflow that triggers the weather processing task."
  type        = string
}

variable "workflow_sa_name" {
  description = "The name of the workflow service account."
  type        = string
}
