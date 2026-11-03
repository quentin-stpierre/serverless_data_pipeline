variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "git_repository_url" {
  description = "The URL of the Git repository"
  type        = string
}

variable "default_branch" {
  description = "The default Git branch for Dataform"
  type        = string
  default     = "main"
}
