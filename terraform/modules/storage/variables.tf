variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "bucket_name" {
  description = "The name of the GCS bucket for raw data"
  type        = string
}

variable "cloud_function_sa_email" {
  description = "The service account email of the scraper cloud function that writes raw data"
  type        = string
  default     = ""
}
