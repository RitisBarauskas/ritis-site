# Infrastructure

Everything the API needs on Google Cloud, in project `ritis-dev` (`europe-west1`): Firestore with TTL on `expire_at`, Artifact Registry, the `ritis-api` Cloud Run service with its service account, secrets in Secret Manager, the notice sweep in Cloud Scheduler and a monthly budget alert. Firebase Hosting forwards `/api/**` to the service (`firebase.json`).

State is kept on the owner's machine (`terraform.tfstate`, git-ignored): it holds the sweep token that Cloud Scheduler presents. Secret values never pass through Terraform or this repository.

## First time

Needs [gcloud](https://cloud.google.com/sdk/docs/install), Terraform 1.15, Docker, and the project on the Blaze plan.

```sh
gcloud auth login
gcloud auth application-default login
cd infra
terraform init
```

1. Create the registry and the secrets (empty), so an image and values can be put there:

   ```sh
   terraform apply -target=google_artifact_registry_repository.api -target=google_secret_manager_secret.this
   ```

2. Put the secret values in. Each command reads the value from the terminal, so it never appears in a command line, a file or the shell history:

   ```sh
   gcloud secrets versions add flitt-secret-key   --data-file=-   # Flitt merchant key ("test" for the test merchant)
   gcloud secrets versions add telegram-bot-token --data-file=-   # from @BotFather
   openssl rand -hex 32 | gcloud secrets versions add sweep-token --data-file=-
   ```

   Type the value, press Enter, then Ctrl-D (Ctrl-Z, Enter on Windows).

3. Build and push the API image (from the repository root), then apply the rest with its digest:

   ```sh
   gcloud auth configure-docker europe-west1-docker.pkg.dev
   docker build -f api/Dockerfile -t europe-west1-docker.pkg.dev/ritis-dev/api/ritis-api:$(git rev-parse --short HEAD) .
   docker push europe-west1-docker.pkg.dev/ritis-dev/api/ritis-api:$(git rev-parse --short HEAD)
   cd infra && terraform apply -var api_image=europe-west1-docker.pkg.dev/ritis-dev/api/ritis-api@sha256:…
   ```

   `terraform.tfvars` (git-ignored) holds the rest: `billing_account`, `budget_amount`, `telegram_chat_id`.

4. Deploy the site, so Hosting forwards `/api/**`: `npx firebase-tools deploy --only hosting --project ritis-dev`.

## A new version of the API

Build and push as in step 3, then `terraform apply -var api_image=…@sha256:…`. Site and API go out from the same commit.
