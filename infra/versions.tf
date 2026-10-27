terraform {
  required_version = ">= 1.6"

  required_providers {
    google  = { source = "hashicorp/google", version = "~> 8.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }

  # State lives in a GCS bucket you create once (see infra/README.md):
  #   terraform init -backend-config="bucket=<project-id>-tfstate"
  backend "gcs" {
    prefix = "lawhub"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  # Budgets API calls are billed to this project when using user credentials.
  user_project_override = true
  billing_project       = var.project_id
}
