# General
project_name    = "Serverless Data Pipeline"
project_id      = "serverless-data-pipeline-111"
region          = "europe-west1"
billing_account = "017F1D-A6D67E-93CD39"
org_id          = "97533724144"
folder_id       = "501022756737"

# Cloud Scheduler
workflow_trigger_name = "weather-workflow-trigger"
scheduler_sa_name     = "weather-scheduler-sa"

# Workflows
workflow_sa_name      = "weather-pipeline-sa"
weather_workflow_name = "weather-data-pipeline"

# Cloud Function
cloud_function_sa_name = "fetch-weather-sa"
cloud_function_name    = "fetch-weather"

# PubSub
topic_name           = "weather-data"
bq_subscription_name = "weather-data-bq"

# BigQuery
dataset_id = "processed_weather_data"
table_id   = "transformed_weather_data"

# Monitoring
alert_email_address = "quentin.st-pierre@devoteam.com"

# CI/CD
terraform_cicd_sa         = "terraform-ci-sa"
cloud_build_trigger_name  = "terraform-plan-on-pr"
github_owner              = "quentin-stpierre"
github_repo               = "serverless_data_pipeline"
terraform_apply_approvers = ["user:quentin.st-pierre@devoteam.com"]

# URL = "https://api.openweathermap.org/data/2.5/weather?lat=50.8503&lon=4.3517&units=metric&appid={YOUR_API_KEY}"
