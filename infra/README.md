# Deploying LawHub (Cloud Run + Neon, private beta)

What runs where:

| Piece | Where | Cost guard |
|---|---|---|
| Web app + MCP server | Google Cloud Run, 1 instance max, scales to zero | free tier; budget + kill switch |
| Database | Neon Postgres (free plan) | no card, stops at plan limits instead of billing |
| Images | Artifact Registry, last 3 kept | free storage tier |
| Secrets | Secret Manager | free tier |
| CI, deploys, backups, data import | GitHub Actions | 2,000 free min/month on private repos; keep the spending limit at $0 |

Terraform (this directory) creates the GCP side once, from your machine.
After that, every push to `main` deploys through GitHub Actions
(`.github/workflows/deploy.yml`) without any stored Google keys: Actions
logs in with Workload Identity Federation, and only `main` of this
repository is allowed to.

## One-time setup

You need [gcloud](https://cloud.google.com/sdk/docs/install) and
[Terraform](https://developer.hashicorp.com/terraform/install) installed locally.

### 1. Neon (database)

1. Sign up at neon.tech, create a project `lawhub`: Postgres 17, region
   **AWS Europe Central 1 (Frankfurt)**.
2. On the dashboard, copy two connection strings:
   - **pooled** (connection pooling on, host contains `-pooler`) for the app,
   - **direct** (pooling off) for backups and the data import.
3. Put the **pooled** one into Google Secret Manager (keeps the password out
   of Terraform): console → *Security → Secret Manager* (enable the API if
   asked) → *Create secret*, name **`lawhub-database-url`**, value = the
   pooled connection string. Or from a terminal:
   `printf '%s' '<pooled url>' | gcloud secrets create lawhub-database-url --data-file=-`
4. Put the **direct** one into GitHub as the secret `NEON_DIRECT_URL` (step 4 below).

### 2. Google Cloud project

```bash
gcloud auth login
gcloud auth application-default login
gcloud projects create lawhub-beta-<random digits>        # or use the console
gcloud billing accounts list                             # note the ACCOUNT_ID
gcloud billing projects link <project-id> --billing-account <ACCOUNT_ID>
gcloud config set project <project-id>

# Bucket for Terraform state
gcloud storage buckets create gs://<project-id>-tfstate --location=europe-west1 --uniform-bucket-level-access
```

### 3. Terraform

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in project, billing account, your email
terraform init -backend-config="bucket=<project-id>-tfstate"
terraform apply
```

The first apply enables a dozen APIs; if a resource fails right after with
"API not enabled" or a missing service agent, wait a minute and run
`terraform apply` again.

### 4. GitHub

In the repository settings → *Secrets and variables* → *Actions*:

- **Variables**: add each key/value from `terraform output github_variables`.
- **Secrets**: `NEON_DIRECT_URL` = the direct Neon connection string.

Also check *Settings → Billing* on your GitHub account: the Actions spending
limit should be $0.

### 5. First deploy

Push or merge to `main`. The *Deploy* workflow runs the tests on Postgres,
builds the image, deploys it and checks `/healthz`. The site is at
`terraform output url`.

### 6. Load the law data

*Actions → Import law data → Run workflow* (seed `pl_driving`). It fetches
only the seeded acts from nalegalu and imports them into Neon.

### 7. Log in

Sign up on the site with an email from `signup_allowlist`. For the Django
admin, create a superuser from your machine:

```bash
DATABASE_URL="<direct Neon URL>" python manage.py createsuperuser
```

### 8. Connect your AI

`/connect/` on the site shows the MCP URL (`terraform output mcp_url`) and
setup steps for Claude and Claude Code.

## Cost guards

- Cloud Run: `max_instance_count = 1`, `min_instance_count = 0`, CPU only while
  serving requests. A traffic spike can't scale into a bill.
- Budget (`budget_amount`, in your billing currency): email alerts at 50%,
  90% and 100%. At 100% the `lawhub-billing-kill-switch` function **unlinks
  billing from the project**, which stops all paid services. Billing data
  lags by a few hours, so a small overshoot is possible. To recover, re-link
  billing in the console (Billing → My projects).
- No Cloud SQL, no load balancer, no always-on instances.

## Day to day

- Deploy: push to `main`.
- Infra changes (env vars, allowlist, limits): edit `*.tf` / `terraform.tfvars`, run `terraform apply`.
- Backups: *Database backup* workflow, daily at 02:17 UTC, artifacts kept 14 days.
  Restore with `pg_restore --clean --no-owner -d "<direct Neon URL>" lawhub.dump`.
- Kill switch tests: `cd infra/kill_switch && pip install -r requirements.txt pytest && python -m pytest`.
