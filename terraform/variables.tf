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

variable "dataset_id" {
  description = "The id of the dataset where the processed weather data is stored."
  type        = string
}

variable "table_id" {
  description = "The id of the table where the processed weather data is stored."
  type        = string
}
