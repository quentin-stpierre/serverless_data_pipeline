# General
project_name    = "Serverless Data Pipeline"
project_id      = "serverless-data-pipeline-111"
region          = "europe-west1"
billing_account = "017F1D-A6D67E-93CD39"
org_id          = "97533724144"
folder_id       = "501022756737"

# Cloud Scheduler & Flight Targets
scheduler_sa_name = "flights-scheduler-sa"
flight_searches = {
  canada_july = {
    schedule           = "0 9 * * 1,4"
    origin             = "BRU"
    destination        = "YUL"
    start_date         = "2027-07-01"
    trip_length        = 24
    flexibility_window = 2
    currency           = "EUR"
    seat               = "economy"
  },
  guatemala_april = {
    schedule           = "0 10 * * 2,5"
    origin             = "BRU"
    destination        = "GUA"
    start_date         = "2027-04-10"
    trip_length        = 18
    flexibility_window = 1
    currency           = "EUR"
    seat               = "economy"
  }
}

# Workflows
workflow_sa_name     = "flights-pipeline-sa"
flight_workflow_name = "flights-data-pipeline"

# Cloud Function
cloud_function_sa_name = "fetch-flights-sa"
cloud_function_name    = "fetch-flights"

# Storage
raw_data_bucket_name = "serverless-data-pipeline-111-raw-data"

# BigQuery
dataset_id = "raw_flight_data"
table_id   = "ext_google_flights"

# Monitoring
alert_email_address = "quentin.st-pierre@devoteam.com"

# CI/CD
terraform_cicd_sa         = "terraform-ci-sa"
cloud_build_trigger_name  = "terraform-plan-on-pr"
github_owner              = "quentin-stpierre"
github_repo               = "serverless_data_pipeline"
terraform_apply_approvers = ["user:quentin.st-pierre@devoteam.com"]
