resource "google_bigquery_dataset" "dataset" {
  project                    = var.project_id
  dataset_id                 = var.dataset_id
  description                = "Dataset for storing OpenWeather Map Data after transformations."
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env = "dev"
  }
}

resource "google_bigquery_table" "table" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = var.table_id
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  labels = {
    env = "dev"
  }

  schema = <<EOF
[
  {
    "name": "location",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Location name (e.g., Brussels)"
  },
  {
    "name": "country",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Two-letter country code"
  },
  {
    "name": "temperature_c",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Temperature in Celsius"
  },
  {
    "name": "temperature_f",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Temperature in Fahrenheit"
  },
  {
    "name": "feels_like_c",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Feels-like temperature in Celsius"
  },
  {
    "name": "feels_like_f",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Feels-like temperature in Fahrenheit"
  },
  {
    "name": "humidity",
    "type": "INTEGER",
    "mode": "NULLABLE",
    "description": "Humidity percentage"
  },
  {
    "name": "pressure",
    "type": "INTEGER",
    "mode": "NULLABLE",
    "description": "Atmospheric pressure in hPa"
  },
  {
    "name": "wind_speed_mps",
    "type": "FLOAT",
    "mode": "NULLABLE",
    "description": "Wind speed in meters per second"
  },
  {
    "name": "weather_condition",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Group of weather parameters (Rain, Snow, Clouds, etc.)"
  },
  {
    "name": "weather_description",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Weather condition description"
  },
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Event timestamp of the extraction and transformation"
  }
]
EOF
}
