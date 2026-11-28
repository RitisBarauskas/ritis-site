terraform {
  required_version = ">= 1.15"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
  # State stays on the owner's machine (infra/README.md): it holds the sweep token Cloud
  # Scheduler presents, so it is never committed.
}

provider "google" {
  project = var.project_id
  region  = var.region
  # The budget API is called against this project's quota, not the provider's.
  user_project_override = true
  billing_project       = var.project_id
}
