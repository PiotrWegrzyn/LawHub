output "url" {
  value = local.public_url
}

output "mcp_url" {
  value = "${local.public_url}/mcp"
}

# Set these as GitHub repository *variables* (Settings → Secrets and variables → Actions → Variables).
output "github_variables" {
  value = {
    GCP_PROJECT_ID    = var.project_id
    GCP_REGION        = var.region
    GCP_WIF_PROVIDER  = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER_SA   = google_service_account.deployer.email
    GCP_IMAGE_REPO    = local.image_repo
    CLOUD_RUN_SERVICE = google_cloud_run_v2_service.app.name
  }
}
