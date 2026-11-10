# Pre-Production Code Review: Serverless Flight Tracking Pipeline

### Overall Verdict: ⛔ **BLOCKED (Not Production-Ready)**

While the overall serverless architecture (Cloud Scheduler → Cloud Workflows → Cloud Function Scraper → GCS Landing → BigQuery BigLake → Dataform Medallion Transforms → Monitoring) is well-conceived, there are **critical functional, infrastructure, and CI/CD blockers** that will cause deployment failures, silent data loss in production, or security risks.

---

## 1. Critical Blocker Issues (Must Fix Before Pushing)

### 1.1 Silent Data Drop in Dataform Staging (`definitions/staging/stg_google_flights.sqlx`)
* **Problem**: The staging model filters raw records with:
  ```sql
  WHERE type != 'seed'
  ```
  While the initial mock seed specifies `type: "seed"`, actual scraped flight records emitted by `fast_flights` do not define a `type` field, defaulting to `NULL`. In ANSI SQL three-valued logic, `NULL != 'seed'` evaluates to `UNKNOWN` (treated as `FALSE` in `WHERE` clauses).
* **Impact**: **100% of real scraped flight data is dropped.** Downstream tables (`dim_flight_itinerary`, `fct_flight_prices`, and `mart_price_alerts`) will remain permanently empty.
* **Fix**: Update the filter to:
  ```sql
  WHERE COALESCE(type, '') != 'seed'
  -- or: WHERE (type IS NULL OR type != 'seed')
  ```

### 1.2 Surrogate Key Returns `NULL` on Missing Fields (`definitions/staging/stg_google_flights.sqlx`)
* **Problem**: `flight_itinerary_key` is calculated using `CONCAT()`:
  ```sql
  TO_HEX(MD5(CONCAT(search_name, '|', origin_airport, '|', destination_airport, '|', CAST(outbound_date AS STRING), '|', COALESCE(CAST(return_date AS STRING), ''), '|', airlines, '|', trip_type, '|', CAST(is_best_flight AS STRING))))
  ```
  In BigQuery SQL, `CONCAT(...)` returns `NULL` if **any** parameter is `NULL`. `airlines`, `origin_airport`, or other fields can occasionally be `NULL`.
* **Impact**: `flight_itinerary_key` becomes `NULL`, violating the `uniqueKey` constraint of `dim_flight_itinerary` and corrupting downstream joins and deduplication.
* **Fix**: Wrap every attribute within `CONCAT` in `COALESCE(...)`, e.g., `COALESCE(airlines, 'UNKNOWN')`.

### 1.3 Terraform DAG Circular Dependency / Bootstrap Failure (`terraform/main.tf` & `modules/dataform`)
* **Problem**: In `terraform/main.tf`, `module.workflows` specifies `depends_on = [..., module.dataform]`. However, `modules/dataform/main.tf` attempts to grant `roles/iam.serviceAccountUser` on `workflow_sa_email`:
  ```hcl
  resource "google_service_account_iam_member" "workflow_act_as_dataform_runner" {
    service_account_id = google_service_account.dataform_runner.name
    role               = "roles/iam.serviceAccountUser"
    member             = "serviceAccount:${var.workflow_sa_email}"
  }
  ```
* **Impact**: On initial greenfield deployment (`terraform apply`), `module.dataform` executes before `module.workflows`. Because `flights-pipeline-sa` does not exist yet, Terraform fails with `Error 400: Service account flights-pipeline-sa does not exist`.
* **Fix**: Move the `google_service_account_iam_member.workflow_act_as_dataform_runner` binding into `modules/workflows/main.tf` where the service account is created, or instantiate service accounts in a shared root identity module.

### 1.4 Unprovisioned Secret Version Breaks Dataform Repository (`terraform/modules/dataform/main.tf`)
* **Problem**: `google_dataform_repository.flights_dataform` sets:
  ```hcl
  authentication_token_secret_version = "${google_secret_manager_secret.github_token.id}/versions/latest"
  ```
  However, Terraform only provisions the secret container (`google_secret_manager_secret`), with no `google_secret_manager_secret_version` created.
* **Impact**: `terraform apply` fails when GCP attempts to resolve `/versions/latest` of an empty secret.
* **Fix**: Provision a placeholder version via Terraform or document and automate the secret payload insertion prior to running Terraform.

### 1.5 CI/CD Plan Hash Misses Code & Variable Changes (`cloudbuild.plan.yaml` & `cloudbuild.apply.yaml`)
* **Problem**: The hash check used to link plan and apply stages computes:
  ```bash
  TF_HASH=$$(find . -name '*.tf' -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
  ```
* **Impact**: If Python scraper code under `functions/fetch_flights/` is updated, or `terraform.tfvars` is modified, `TF_HASH` remains unchanged. The apply step on `main` will either apply a stale plan or fail to detect functional changes.
* **Fix**: Update the hashing command to include `terraform/` (`*.tf`, `*.tfvars`), `functions/`, and `workflow_settings.yaml`.

### 1.6 Cross-Search Alert Leakage (`terraform/modules/workflows/workflow.yaml`)
* **Problem**: In `workflow.yaml`, the alert evaluation step runs:
  ```sql
  SELECT itinerary_name, latest_price, min_historical_price, price_drop_amount, observation_date
  FROM `${project_id}.${marts_dataset}.mart_price_alerts`
  WHERE should_alert = TRUE
  LIMIT 1
  ```
* **Impact**: The query does not filter by `search_name = '${search_name}'`. If route A triggers a price drop alert, subsequent workflow iterations for route B will read route A's record and emit a false alert for the wrong route.
* **Fix**: Add `AND search_name = '$${search_name}'` to the query.

---

## 2. High Priority Issues (Architecture, Security & Resilience)

### 2.1 Overly Broad IAM Roles
* **CI/CD Service Account (`modules/cicd/main.tf`)**: Granted `roles/editor` and `roles/iam.securityAdmin`.
  * *Remediation*: Restrict to specific least-privilege roles (`roles/cloudfunctions.developer`, `roles/workflows.admin`, `roles/bigquery.admin`, `roles/storage.admin`, `roles/iam.serviceAccountUser`).
* **Dataform Runner SA (`modules/dataform/main.tf`)**: Granted project-level `roles/bigquery.dataEditor`.
  * *Remediation*: Scope permissions to the specific datasets (`raw_flight_data`, `flight_staging`, `flight_marts`, `flight_assertions`) using `google_bigquery_dataset_iam_member`.
* **Scheduler SA (`modules/scheduler/main.tf`)**: Granted project-level `roles/workflows.invoker`.
  * *Remediation*: Bind role directly to the specific workflow using `google_workflows_workflow_iam_member`.

### 2.2 Missing Storage Bucket Public Access Prevention
* **Problem**: None of the 4 buckets (`tf_state`, `raw_flights_data_bucket`, `function_bucket`, `tf_plans`) set `public_access_prevention = "enforced"`.
* **Fix**: Add `public_access_prevention = "enforced"` across all `google_storage_bucket` resources in `modules/storage/main.tf`.

### 2.3 Data Loss Risks: Accidental Deletion Protection
* `google_bigquery_dataset` (`dataset`, `staging`, `marts`) have `delete_contents_on_destroy = true`.
* `google_bigquery_table.table` and `google_workflows_workflow.pipeline_workflow` have `deletion_protection = false`.
* **Fix**: For production environments, set `delete_contents_on_destroy = false` and `deletion_protection = true` to guard against catastrophic accidental teardowns.

### 2.4 Scraper Resilience & Dependency Integrity (`functions/fetch_flights/`)
* **Undeclared Dependency**: `fast_flights_scraper.py` imports `from primp import Client`, but `primp` is omitted from `requirements.txt`.
* **Unused & Unpinned Dependencies**: `google-search-results`, `google-cloud-secret-manager`, and `google-auth` are present but never imported. Dependencies use unpinned `>=` without a lockfile.
* **Session Churn & Anti-Bot Failures**: A new `Client(impersonate="chrome_145")` is created on every single call (dozens of times per invocation). Network timeouts, HTTP 429 (rate-limiting), and HTTP 403 throw unhandled exceptions because only `FlightsNotFound` is caught.
* **Hardcoded Consent Cookie**: The `SOCS` cookie header is hardcoded and will eventually expire.

### 2.5 Cloud Workflows Missing Error Retries & Unbounded Polling
* Calls to `scrape_flights` and Dataform compilation lack retry policies for transient network or 503 errors.
* `check_dataform_status` polls `sys.sleep 5` in an unbounded loop with no timeout or iteration ceiling. If a Dataform job hangs, the workflow will run until execution timeout.

### 2.6 Absence of Automated Testing & Assertions
* No Python unit/mock tests (`pytest`) for scraping logic or GCS payload formatting.
* The `flight_assertions` BigQuery dataset is created, but no Dataform assertions exist in `definitions/` to validate schema integrity or data sanity (e.g., price > 0, non-null keys).

---

## 3. Medium & Low Priority Improvements

1. **Misleading Documentation (`README.md`)**:
   * `README.md` describes an outdated "Serverless Weather Data Pipeline" with OpenWeatherMap. Update it to document the flight tracking pipeline as described in `PIPELINE.md`.
2. **Sensitive Information in Git (`terraform/terraform.tfvars`)**:
   * Contains actual corporate billing account IDs, org IDs, folder IDs, and email addresses committed to the repository.
   * *Remediation*: Rename to `terraform.tfvars.example` with placeholder values, and add `*.tfvars` to `.gitignore`.
3. **Terraform Provider Locking**:
   * `.terraform.lock.hcl` is excluded in `.gitignore`. It should be tracked in version control to guarantee deterministic provider versions across environments.
4. **Structured Logging**:
   * `main.py` has no logging; `fast_flights_scraper.py` uses raw `print()`. Replace with Google Cloud structured logging or standard Python `logging`.
5. **BigQuery MERGE Deduplication**:
   * `fct_flight_prices.sqlx` merges on `observation_id = MD5(CONCAT(flight_itinerary_key, '|', scraped_at_date))`. If the scraper runs twice in a day or finds identical itineraries, BigQuery's MERGE fails if source rows are not deduplicated. Add a `QUALIFY ROW_NUMBER() OVER (PARTITION BY observation_id ORDER BY price ASC) = 1` clause.

---

## Actionable Remediation Checklist

```markdown
[ ] 1. Fix definitions/staging/stg_google_flights.sqlx:
       - Change WHERE type != 'seed' to WHERE COALESCE(type, '') != 'seed'
       - Wrap CONCAT elements for flight_itinerary_key with COALESCE()
[ ] 2. Fix definitions/marts/fct_flight_prices.sqlx:
       - Deduplicate source rows by observation_id
[ ] 3. Fix terraform/main.tf & modules/dataform/main.tf:
       - Move workflow_act_as_dataform_runner IAM binding to modules/workflows/main.tf
       - Add secret version or pre-apply token creation for dataform-github-token
[ ] 4. Fix terraform/modules/workflows/workflow.yaml:
       - Add 'AND search_name = $${search_name}' to query_price_alerts
       - Add retry blocks and max polling loop counter
[ ] 5. Harden IAM & Storage in Terraform:
       - Replace roles/editor and roles/iam.securityAdmin on CI/CD SA with granular roles
       - Add public_access_prevention = "enforced" to all GCS buckets
       - Set deletion_protection = true on BigQuery datasets and Workflows
[ ] 6. Clean up functions/fetch_flights/:
       - Add primp to requirements.txt, remove unused libraries, pin versions
       - Reuse Client instance across searches and add retry/backoff for HTTP 429/timeouts
       - Implement structured logging
[ ] 7. Update cloudbuild.plan.yaml and cloudbuild.apply.yaml:
       - Include functions/ and terraform.tfvars in TF_HASH
[ ] 8. Hygiene & Documentation:
       - Replace README.md with actual flight pipeline documentation
       - Track .terraform.lock.hcl in git; untrack terraform.tfvars (create .example)
```
