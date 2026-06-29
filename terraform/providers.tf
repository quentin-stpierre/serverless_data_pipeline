terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.0"
    }
  }

  # NOTE: To use GCS as a backend, the bucket must already exist.
  # 1. Run 'terraform apply' with this block commented out to create the bucket.
  # 2. Uncomment this block and run 'terraform init' to migrate state.
  backend "gcs" {
    bucket = "serverless-data-pipeline-111-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  region = var.region
}
