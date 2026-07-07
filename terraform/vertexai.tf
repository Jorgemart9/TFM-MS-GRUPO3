resource "google_vertex_ai_endpoint" "credit_risk_endpoint" {
  name         = "credit-risk-endpoint"
  display_name = "Credit Risk Endpoint"
  location     = "europe-west1"
}

