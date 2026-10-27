data "google_project" "this" {}

locals {
  service_name = "lawhub"
  # Cloud Run's deterministic URL, known before the service exists, so the
  # app can be told its own public address (OAuth/MCP metadata needs it).
  public_host = "${local.service_name}-${data.google_project.this.number}.${var.region}.run.app"
  public_url  = "https://${local.public_host}"
  image_repo  = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# --- container images ---------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  repository_id = "lawhub"
  location      = var.region
  format        = "DOCKER"

  # Stay inside the free storage tier: keep only the latest few images.
  cleanup_policies {
    id     = "keep-latest-3"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
  cleanup_policies {
    id     = "delete-older"
    action = "DELETE"
    condition {
      older_than = "86400s"
    }
  }

  depends_on = [google_project_service.apis]
}

# --- secrets ------------------------------------------------------------------

resource "random_password" "django_secret_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(["django-secret-key", "database-url"])
  secret_id = "lawhub-${each.value}"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "django_secret_key" {
  secret      = google_secret_manager_secret.secrets["django-secret-key"].id
  secret_data = random_password.django_secret_key.result
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.secrets["database-url"].id
  secret_data = var.database_url
}

# --- the app ------------------------------------------------------------------

resource "google_service_account" "run" {
  account_id   = "lawhub-run"
  display_name = "LawHub Cloud Run runtime"
}

resource "google_secret_manager_secret_iam_member" "run_reads_secrets" {
  for_each  = google_secret_manager_secret.secrets
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}

resource "google_cloud_run_v2_service" "app" {
  name                = local.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.run.email
    timeout         = "300s" # MCP responses may stream

    # Cost guard: never more than one instance, none while idle.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    max_instance_request_concurrency = 40

    containers {
      # Placeholder until the first GitHub Actions deploy; later images are
      # rolled out by the deploy workflow (see lifecycle below).
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true # CPU only billed while handling requests
        startup_cpu_boost = true
      }

      env {
        name  = "DJANGO_DEBUG"
        value = "0"
      }
      env {
        name  = "DJANGO_ALLOWED_HOSTS"
        value = local.public_host
      }
      env {
        name  = "LAWHUB_PUBLIC_URL"
        value = local.public_url
      }
      env {
        name  = "LAWHUB_PRIVATE"
        value = "1"
      }
      env {
        name  = "LAWHUB_SIGNUP_ALLOWLIST"
        value = join(",", var.signup_allowlist)
      }
      env {
        name = "DJANGO_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["django-secret-key"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["database-url"].secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 2
        period_seconds        = 3
        failure_threshold     = 20
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.run_reads_secrets,
    google_secret_manager_secret_version.django_secret_key,
    google_secret_manager_secret_version.database_url,
  ]
}

# Reachable from the internet; the app itself requires login (LAWHUB_PRIVATE=1).
# MCP clients and OAuth callbacks can't present Google identity tokens, so
# Cloud Run IAM can't be the gate.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
