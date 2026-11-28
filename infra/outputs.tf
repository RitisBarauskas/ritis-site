output "api_url" {
  description = "Cloud Run's own address; the site reaches the API through Hosting instead."
  value       = google_cloud_run_v2_service.api.uri
}

output "registry" {
  description = "Where API images are pushed."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}
