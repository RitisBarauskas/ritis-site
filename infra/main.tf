locals {
  services = [
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudscheduler.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ]
  # Values are added by the owner with gcloud (infra/README.md), never through Terraform.
  secrets = {
    flitt_secret_key   = "flitt-secret-key"
    telegram_bot_token = "telegram-bot-token"
    sweep_token        = "sweep-token"
  }
}

resource "google_project_service" "this" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# --- images ---------------------------------------------------------------------------------

resource "google_artifact_registry_repository" "api" {
  repository_id = "api"
  location      = var.region
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "drop-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days; the ten most recent stay regardless
    }
  }

  depends_on = [google_project_service.this]
}

# --- bookings -------------------------------------------------------------------------------

# Its location cannot change later: the EU, as the privacy policy states.
resource "google_firestore_database" "default" {
  name                    = "(default)"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  depends_on = [google_project_service.this]
}

# Unpaid bookings and their idempotency keys carry expire_at (api/README.md, «Storage»);
# Firestore deletes them after it. Paid bookings have none and stay.
resource "google_firestore_field" "expire_at" {
  for_each   = toset(["bookings", "idempotency_keys"])
  database   = google_firestore_database.default.name
  collection = each.value
  field      = "expire_at"

  ttl_config {}
  # Never queried: no index, so no index writes to pay for.
  index_config {}
}

# --- secrets --------------------------------------------------------------------------------

resource "google_secret_manager_secret" "this" {
  for_each  = local.secrets
  secret_id = each.value

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.this]
}

data "google_secret_manager_secret_version" "sweep_token" {
  secret = google_secret_manager_secret.this["sweep_token"].id
}

# --- the API --------------------------------------------------------------------------------

resource "google_service_account" "api" {
  account_id   = "ritis-api"
  display_name = "ritis.dev API on Cloud Run"
}

resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = google_service_account.api.member
}

resource "google_secret_manager_secret_iam_member" "api" {
  for_each  = google_secret_manager_secret.this
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.api.member
}

resource "google_cloud_run_v2_service" "api" {
  name                = "ritis-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account = google_service_account.api.email
    # A small site: a handful of instances is plenty and caps what a flood can cost.
    scaling {
      max_instance_count = 3
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      env {
        name  = "RITIS_STORAGE"
        value = "firestore"
      }
      env {
        name  = "RITIS_API_BASE_URL"
        value = var.site_url
      }
      env {
        name  = "RITIS_SITE_URL"
        value = var.site_url
      }
      env {
        name  = "RITIS_FLITT_MERCHANT_ID"
        value = tostring(var.flitt_merchant_id)
      }
      env {
        name  = "RITIS_TELEGRAM_CHAT_ID"
        value = tostring(var.telegram_chat_id)
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      dynamic "env" {
        for_each = local.secrets
        content {
          name = "RITIS_${upper(env.key)}"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.key].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/api/health"
        }
      }
    }
  }

  depends_on = [
    google_firestore_database.default,
    google_project_iam_member.api_firestore,
    google_secret_manager_secret_iam_member.api,
  ]
}

# The site calls the API through Firebase Hosting, which reaches Cloud Run as any caller would.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- the notice sweep -----------------------------------------------------------------------

# Delivers owner notices a down messenger left behind (api/README.md).
resource "google_cloud_scheduler_job" "sweep" {
  name      = "ritis-notice-sweep"
  region    = var.region
  schedule  = "*/10 * * * *"
  time_zone = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "${var.site_url}/api/internal/notices"
    headers = {
      Authorization = "Bearer ${data.google_secret_manager_secret_version.sweep_token.secret_data}"
    }
  }

  retry_config {
    retry_count = 1
  }

  depends_on = [google_project_service.this]
}

# --- spending -------------------------------------------------------------------------------

data "google_project" "this" {}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "ritis-dev monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      units = tostring(var.budget_amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.this]
}
