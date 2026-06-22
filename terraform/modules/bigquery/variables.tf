variable "project_id" {
  description = "The ID of the GCP project where the BigQuery resources will be created."
  type        = string
}

variable "dataset_id" {
  description = "The ID of the dataset where the processed weather data is stored."
  type        = string
}

variable "table_id" {
  description = "The ID of the table where the processed weather data is stored."
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}
