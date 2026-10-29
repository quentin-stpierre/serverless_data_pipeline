variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
}

variable "workflow_name" {
  description = "The name of the Cloud Workflow to trigger"
  type        = string
}

variable "scheduler_sa_name" {
  description = "The name of the Cloud Scheduler service account."
  type        = string
}

variable "flight_searches" {
  description = "Map of flight search configurations to schedule"
  type = map(object({
    schedule           = string
    origin             = string
    destination        = string
    start_date         = string
    trip_length        = number
    flexibility_window = number
    currency           = optional(string, "EUR")
    seat               = optional(string, "economy")
    adults             = optional(number, 1)
    max_stops          = optional(number, 0)
  }))
}
