variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "cloud_function_sa_name" {
  description = "The name of the cloud function service account."
  type        = string
}

variable "cloud_function_name" {
  description = "The name of the cloud function."
  type        = string
}

variable "raw_data_bucket_name" {
  description = "The name of the GCS bucket to store raw flight data"
  type        = string
}
