data "google_project" "project" {
  project_id = var.project_id
}

resource "google_pubsub_topic" "weather_topic" {
  name    = "weather-data"
  project = var.project_id
}

resource "google_project_iam_member" "pubsub_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "pubsub_bq_metadata_viewer" {
  project = var.project_id
  role    = "roles/bigquery.metadataViewer"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription" "bq_subscription" {
  name    = "weather-data-bq"
  topic   = google_pubsub_topic.weather_topic.name
  project = var.project_id

  bigquery_config {
    table            = "${var.project_id}.${var.dataset_id}.${var.table_id}"
    use_table_schema = true
    use_topic_schema = false
    write_metadata   = false
  }

  depends_on = [
    google_project_iam_member.pubsub_bq_editor,
    google_project_iam_member.pubsub_bq_metadata_viewer
  ]
}
