variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "dataset_id" {
  description = "The BigQuery dataset ID"
  type        = string
}

variable "table_id" {
  description = "The BigQuery table ID"
  type        = string
}

variable "topic_name" {
  description = "The name of the PubSub topic"
  type        = string
}

variable "bq_subscription_name" {
  description = "The name of BigQuery's PubSub subscription."
  type        = string
}
