# Notary API - GCP Deployment Checklist

## 🎯 Pre-Deployment Setup

### Local Machine
- [ ] Install `gcloud` CLI: https://cloud.google.com/sdk/docs/install
- [ ] Authenticate: `gcloud auth login`
- [ ] Set default project: `gcloud config set project notary-management-web-platform`
- [ ] Install Docker Desktop
- [ ] Clone repository locally

### GCP Console
- [ ] Verify project exists: `notary-management-web-platform`
- [ ] Enable billing on the project
- [ ] Have Viewer/Editor role permissions

---

## 📦 Option 1: Manual Build & Push (One-time)

```bash
# 1. Navigate to project directory
cd /path/to/notary-management-web-platform

# 2. Run one-click deployment script
chmod +x deploy-to-gcp.sh
./deploy-to-gcp.sh

# 3. Follow prompts to deploy to Cloud Run or GKE
```

**What it does:**
- Enables required GCP APIs
- Creates Artifact Registry repository
- Builds and pushes Docker image
- Provides deployment commands

---

## 🔄 Option 2: Cloud Build CI/CD (Automated)

### Setup
```bash
# 1. Connect GitHub repository to Cloud Build
# Go to: https://console.cloud.google.com/cloud-build/triggers
# Click "Create Trigger"
# Select your GitHub repo and authorize

# 2. Create trigger with these settings:
#    Name: notary-api-build
#    Event: Push to branch
#    Branch: ^main$
#    Build configuration: Cloud Build configuration file
#    Location: / (root)
#    File name: cloudbuild.yaml

# 3. Authorize Cloud Build service account
gcloud projects add-iam-policy-binding notary-management-web-platform \
  --member=serviceAccount:$(gcloud projects describe notary-management-web-platform --format='value(projectNumber)')@cloudbuild.gserviceaccount.com \
  --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding notary-management-web-platform \
  --member=serviceAccount:$(gcloud projects describe notary-management-web-platform --format='value(projectNumber)')@cloudbuild.gserviceaccount.com \
  --role=roles/run.admin
```

### Usage
- [ ] Push code to `main` branch
- [ ] Cloud Build automatically triggers (view at: https://console.cloud.google.com/cloud-build)
- [ ] Image pushed to Artifact Registry
- [ ] (Optional) Automatically deploys to Cloud Run

---

## 🚀 Option 3: GitHub Actions (Recommended)

### Prerequisites
1. Set up Workload Identity Federation (WIF) for keyless authentication:
   ```bash
   # Create service account
   gcloud iam service-accounts create github-actions \
     --display-name="GitHub Actions for Notary API" \
     --project=notary-management-web-platform

   # Grant permissions
   gcloud projects add-iam-policy-binding notary-management-web-platform \
     --member=serviceAccount:github-actions@notary-management-web-platform.iam.gserviceaccount.com \
     --role=roles/artifactregistry.writer

   gcloud projects add-iam-policy-binding notary-management-web-platform \
     --member=serviceAccount:github-actions@notary-management-web-platform.iam.gserviceaccount.com \
     --role=roles/run.admin
   ```

2. Create Workload Identity Provider:
   ```bash
   gcloud iam workload-identity-pools create "github" \
     --project="notary-management-web-platform" \
     --location="global" \
     --display-name="GitHub Actions Pool"

   gcloud iam workload-identity-pools providers create-oidc "github" \
     --project="notary-management-web-platform" \
     --location="global" \
     --workload-identity-pool="github" \
     --display-name="GitHub Provider" \
     --attribute-mapping="google.subject=assertion.sub,assertion.aud=assertion.aud" \
     --issuer-uri="https://token.actions.githubusercontent.com"
   ```

3. Grant service account access to WIF:
   ```bash
   gcloud iam service-accounts add-iam-policy-binding github-actions@notary-management-web-platform.iam.gserviceaccount.com \
     --project="notary-management-web-platform" \
     --role="roles/iam.workloadIdentityUser" \
     --member="principalSet://iam.googleapis.com/projects/notary-management-web-platform/locations/global/workloadIdentityPools/github/attribute.repository/<YOUR_GITHUB_USERNAME>/<REPO_NAME>"
   ```

4. Add GitHub Secrets:
   - Go to: GitHub Repo > Settings > Secrets and variables > Actions
   - [ ] Add `WIF_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github`
   - [ ] Add `WIF_SERVICE_ACCOUNT`: `github-actions@notary-management-web-platform.iam.gserviceaccount.com`

### Usage
- [ ] GitHub Actions workflow at `.github/workflows/gcp-deploy.yml` triggers on push to `main` or `develop`
- [ ] Builds image, runs tests, pushes to Artifact Registry
- [ ] Deploys to Cloud Run with health check verification

---

## ☁️ Deployment Targets

### Quick Deploy to Cloud Run
```bash
gcloud run deploy notary-api \
  --image=us-central1-docker.pkg.dev/notary-management-web-platform/notary-repository/notary-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --set-env-vars="ENVIRONMENT=production,ALLOWED_ORIGINS=https://yourdomain.com"
```

### Deploy to GKE
```bash
# Create cluster
gcloud container clusters create notary-cluster \
  --region=us-central1 \
  --num-nodes=2 \
  --machine-type=e2-standard-2

# Get credentials
gcloud container clusters get-credentials notary-cluster --region=us-central1

# Deploy
kubectl apply -f k8s/deployment.yaml

# Verify
kubectl get pods -n notary-prod
```

---

## ✅ Post-Deployment Verification

### Cloud Run
```bash
# Get service URL
gcloud run services describe notary-api --region=us-central1

# Test health endpoint
curl https://<SERVICE_URL>/api/health
```

### GKE
```bash
# Port forward to test locally
kubectl port-forward -n notary-prod svc/notary-api 8080:80

# Test
curl http://localhost:8080/api/health
```

### View Logs
```bash
# Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50

# GKE logs
kubectl logs -n notary-prod -l app=notary-api -f
```

---

## 📊 Monitoring

- [ ] Set up Cloud Monitoring dashboard: https://console.cloud.google.com/monitoring
- [ ] Create uptime checks for `/api/health` endpoint
- [ ] Set up alerts for high error rates
- [ ] Enable Cloud Trace for performance monitoring

---

## 🗑️ Cleanup (When Done Testing)

```bash
# Delete Cloud Run service
gcloud run services delete notary-api --region=us-central1

# Or delete GKE cluster
gcloud container clusters delete notary-cluster --region=us-central1

# Or delete Artifact Registry
gcloud artifacts repositories delete notary-repository --location=us-central1
```

---

## 📝 Next Steps

1. **Database Setup**
   - For production: Create Cloud SQL PostgreSQL instance and update DATABASE_URL
   - For development: SQLite works fine locally

2. **API Hardening**
   - Add authentication/authorization (JWT tokens)
   - Set up request rate limiting
   - Add input validation and sanitization

3. **Monitoring**
   - Set up logging aggregation
   - Create dashboards for key metrics
   - Configure alerting policies

4. **Security**
   - Enable VPC Service Controls
   - Set up firewall rules
   - Implement CORS properly with your domain

---

## 🆘 Troubleshooting

**Image push fails:**
- Check authentication: `gcloud auth list`
- Ensure service account has `artifactregistry.writer` role

**Cloud Run deployment fails:**
- Verify image exists: `gcloud artifacts docker images list us-central1-docker.pkg.dev/notary-management-web-platform/notary-repository`
- Check logs: `gcloud logging read "resource.type=cloud_run_revision" --limit=20`

**GitHub Actions secrets not working:**
- Verify `WIF_PROVIDER` and `WIF_SERVICE_ACCOUNT` are set correctly
- Re-create secrets if in doubt

**Health check failing:**
- Ensure port 8080 is exposed in Dockerfile
- Check logs: `gcloud logging read`
