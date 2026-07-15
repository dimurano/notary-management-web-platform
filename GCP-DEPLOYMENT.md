# Notary API - Google Cloud Deployment Guide

## Prerequisites
- GCP account with active project `notary-management-web-platform`
- `gcloud` CLI installed and authenticated: `gcloud auth login`
- Docker installed locally
- Project set: `gcloud config set project notary-management-web-platform`

## Quick Setup (Automated)

```bash
# Make the setup script executable
chmod +x gcp-setup.sh

# Run the automated setup
./gcp-setup.sh
```

This will:
- Enable required GCP APIs
- Create Artifact Registry repository
- Configure Cloud Build service account
- Guide you through GitHub integration

---

## Manual Setup Steps

### 1. Set Project Variables
```bash
export PROJECT_ID="notary-management-web-platform"
export REGION="us-central1"
export REPOSITORY="notary-repository"
export IMAGE_NAME="notary-api"
```

### 2. Enable Required APIs
```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  container.googleapis.com
```

### 3. Create Artifact Registry Repository
```bash
gcloud artifacts repositories create $REPOSITORY \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker repository for Notary API"
```

### 4. Configure Cloud Build Permissions
```bash
# Get project number
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant IAM roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$CLOUD_BUILD_SA \
  --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$CLOUD_BUILD_SA \
  --role=roles/run.admin
```

### 5. Build and Push Image Manually
```bash
# Build locally and push
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest .

# Authenticate Docker
gcloud auth configure-docker $REGION-docker.pkg.dev

# Push
docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest
```

Or use Cloud Build:
```bash
gcloud builds submit --config=cloudbuild.yaml
```

### 6. View Pushed Images
```bash
gcloud artifacts docker images list $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY
```

---

## Deployment Options

### Option A: Cloud Run (Serverless - Recommended for Simple APIs)
```bash
gcloud run deploy notary-api \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=sqlite:///./data/notary_journal.db,ENVIRONMENT=production"
```

### Option B: Google Kubernetes Engine (GKE - Recommended for Production)
```bash
# Create GKE cluster
gcloud container clusters create notary-cluster \
  --region=$REGION \
  --num-nodes=2 \
  --machine-type=e2-standard-2 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=5

# Get credentials
gcloud container clusters get-credentials notary-cluster --region=$REGION

# Deploy
kubectl apply -f k8s/deployment.yaml

# Check deployment
kubectl get deployments -n notary-prod
kubectl get pods -n notary-prod
kubectl logs -n notary-prod -l app=notary-api -f
```

### Option C: Cloud Build GitHub Integration (CI/CD Pipeline)

1. **Connect GitHub Repository**
   - Go to Cloud Console > Cloud Build > Triggers
   - Click "Connect Repository"
   - Select GitHub and authorize
   - Select your repository

2. **Create Build Trigger**
   - Click "Create Trigger"
   - Name: `notary-api-main-build`
   - Event: Push to branch (select `main`)
   - Configuration: Cloud Build configuration file
   - Location: `/ (root directory)` 
   - File name: `cloudbuild.yaml`
   - Click Create

3. **Push to Main to Trigger Build**
   ```bash
   git add .
   git commit -m "Setup CI/CD with Cloud Build"
   git push origin main
   ```

4. **View Build Logs**
   ```bash
   # List builds
   gcloud builds list

   # View build details
   gcloud builds log <BUILD_ID> --stream=true
   ```

---

## Environment Configuration

### For Development (SQLite)
```bash
export DATABASE_URL="sqlite:///./data/notary_journal.db"
export ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8000"
```

### For Production (Cloud SQL PostgreSQL)
1. Create a Cloud SQL PostgreSQL instance:
   ```bash
   gcloud sql instances create notary-db \
     --database-version=POSTGRES_16 \
     --tier=db-f1-micro \
     --region=$REGION
   ```

2. Create database and user:
   ```bash
   gcloud sql databases create notary_db --instance=notary-db
   gcloud sql users create notary_user --instance=notary-db --password
   ```

3. Get connection string:
   ```bash
   gcloud sql instances describe notary-db --format="value(ipAddresses[0].ipAddress)"
   # Format: postgresql://notary_user:PASSWORD@INSTANCE_IP:5432/notary_db
   ```

4. Set in Cloud Run or Kubernetes Secret:
   ```bash
   kubectl create secret generic notary-secrets \
     --from-literal=database-url="postgresql://notary_user:PASSWORD@CLOUD_SQL_IP:5432/notary_db" \
     -n notary-prod
   ```

---

## Monitoring and Logging

### Cloud Run Logs
```bash
gcloud run services describe notary-api --region=$REGION
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=notary-api" --limit 50
```

### GKE Logs
```bash
kubectl logs -n notary-prod -l app=notary-api --all-containers=true -f
kubectl describe pod -n notary-prod <POD_NAME>
```

### Health Checks
```bash
# Test health endpoint after deployment
curl https://<SERVICE_URL>/api/health
```

---

## Cleanup

### Delete Cloud Run Service
```bash
gcloud run services delete notary-api --region=$REGION
```

### Delete GKE Cluster
```bash
gcloud container clusters delete notary-cluster --region=$REGION
```

### Delete Artifact Registry Repository
```bash
gcloud artifacts repositories delete $REPOSITORY --location=$REGION
```

---

## Troubleshooting

**Build fails with "permission denied"**
- Ensure Cloud Build service account has `artifactregistry.writer` role

**Image not pushed to registry**
- Check build logs: `gcloud builds log <BUILD_ID>`
- Verify repository exists: `gcloud artifacts repositories list`

**Cloud Run deployment fails**
- Check image exists: `gcloud artifacts docker images list $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY`
- Verify port 8080 is exposed in Dockerfile

**Database connection error**
- Ensure Cloud SQL instance is accessible from Cloud Run/GKE
- For GKE, use Cloud SQL Proxy sidecar or configure firewall rules
