# Spending guard. GCP has no hard spending cap, so:
#  1. email alerts at 50% / 90% / 100% of the monthly budget (to billing admins),
#  2. at 100% a function unlinks billing from the project, which stops every
#     paid service in it. Billing data lags by hours, so a small overshoot is
#     possible. Re-link billing in the console to bring things back.

resource "google_pubsub_topic" "budget" {
  name       = "lawhub-budget-alerts"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic_iam_member" "budget_publishes" {
  topic  = google_pubsub_topic.budget.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:billing-budget-alert@system.gserviceaccount.com"
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "LawHub monthly budget (kill switch)"

  budget_filter {
    projects        = ["projects/${data.google_project.this.number}"]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      units = tostring(var.budget_amount)
    }
  }

  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }

  all_updates_rule {
    pubsub_topic = google_pubsub_topic.budget.id
  }

  depends_on = [google_project_service.apis]
}

# --- kill switch function -------------------------------------------------------

resource "google_service_account" "kill_switch" {
  account_id   = "lawhub-kill-switch"
  display_name = "LawHub billing kill switch"
}

# Project Billing Manager can link/unlink the project's billing account.
resource "google_project_iam_member" "kill_switch_unlinks_billing" {
  project = var.project_id
  role    = "roles/billing.projectManager"
  member  = "serviceAccount:${google_service_account.kill_switch.email}"
}

resource "google_service_account" "kill_switch_trigger" {
  account_id   = "lawhub-kill-switch-trigger"
  display_name = "Eventarc trigger for the kill switch"
}

resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-functions"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "kill_switch" {
  type        = "zip"
  source_dir  = "${path.module}/kill_switch"
  output_path = "${path.module}/.build/kill_switch.zip"
  excludes    = ["test_main.py", "__pycache__"]
}

resource "google_storage_bucket_object" "kill_switch" {
  name   = "kill_switch-${data.archive_file.kill_switch.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.kill_switch.output_path
}

resource "google_cloudfunctions2_function" "kill_switch" {
  name     = "lawhub-billing-kill-switch"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "stop_billing"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.kill_switch.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = google_service_account.kill_switch.email
    environment_variables = {
      PROJECT_ID = var.project_id
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.budget.id
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.kill_switch_trigger.email
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_service_iam_member" "trigger_invokes_kill_switch" {
  service  = google_cloudfunctions2_function.kill_switch.service_config[0].service
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.kill_switch_trigger.email}"
}
