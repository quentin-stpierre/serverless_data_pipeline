variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "secret_id" {
  description = "The ID of the Secret Manager secret to access"
  type        = string
}

variable "cloud_function_sa_name" {
  description = "The name of the cloud function service account."
  type        = string
}

variable "cloud_function_name" {
  description = "The name of the cloud function processing weather data."
  type        = string
}
