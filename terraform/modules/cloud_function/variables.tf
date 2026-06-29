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
