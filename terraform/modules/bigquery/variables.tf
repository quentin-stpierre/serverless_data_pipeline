variable "project_id" {
  description = "The ID of the GCP project where the BigQuery resources will be created."
  type        = string
}

variable "dataset_id" {
  description = "The ID of the dataset where the flight data is stored."
  type        = string
}

variable "table_id" {
  description = "The ID of the table where the flight data is stored."
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "raw_bucket_name" {
  description = "The GCS bucket name holding the raw JSONL flight data."
  type        = string
}
