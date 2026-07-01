# ==========================================================
# JOB DE CLOUD DATAFLOW (ETL)
# ==========================================================
resource "google_dataflow_job" "pipeline" {
  name              = "etl-pipeline"
  region            = var.region
  template_gcs_path = "gs://dataflow-templates/latest/GCS_Text_to_BigQuery"
  temp_gcs_location = "gs://${google_storage_bucket.output_bucket.name}/tmp_dir"

  service_account_email = google_service_account.sa_dataflow.email
  network               = google_compute_network.vpc.name
  subnetwork            = "regions/${var.region}/subnetworks/${google_compute_subnetwork.subnet.name}"

  parameters = {
    javascriptTextTransformGcsPath      = "gs://${google_storage_bucket.output_bucket.name}/udf.js"
    JSONPath                            = "gs://${google_storage_bucket.output_bucket.name}/schema.json"
    javascriptTextTransformFunctionName = "transform"
    outputTable                         = "${var.project_id}:${google_bigquery_dataset.dataset.dataset_id}.clean_table"
    inputFilePattern                    = "gs://${google_storage_bucket.output_bucket.name}/*.csv"
    bigQueryLoadingTemporaryDirectory   = "gs://${google_storage_bucket.output_bucket.name}/bq_tmp"
  }

  depends_on = [
    google_service_networking_connection.private_vpc_connection,
    google_bigquery_dataset.dataset
  ]
}
