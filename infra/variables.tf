variable "project_id" {
  description = "GCP project id, e.g. lawhub-beta-123456."
  type        = string
}

variable "region" {
  description = "Cloud Run region. europe-west1 is a cheaper (tier 1) region close to Neon's Frankfurt region."
  type        = string
  default     = "europe-west1"
}

variable "billing_account_id" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX), for the budget and kill switch."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget in the billing account's currency. At 100% the kill switch unlinks billing from the project."
  type        = number
  default     = 5
}

variable "github_repository" {
  description = "owner/repo allowed to deploy, exactly as GitHub spells it."
  type        = string
  default     = "PiotrWegrzyn/LawHub"
}

variable "database_url" {
  description = "Neon *pooled* connection string (host contains -pooler)."
  type        = string
  sensitive   = true
}

variable "signup_allowlist" {
  description = "Emails allowed to sign up during the private beta."
  type        = list(string)
  default     = []
}
