#!/bin/bash
# GCP Setup Script for Notary Management Web Platform
# This script configures your GCP project for CI/CD with Cloud Build and Artifact Registry

set -e

# Variables
PROJECT_ID="notary-management-web-platform"
REGION="us-central1"
REPOSITORY="notary-repository"
IMAGE_NAME="notary-api"
GH_REPO="your-github-username/notary-management-web-platform"  # Update this

echo "🔧 Setting up Notary API on Google Cloud..."
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"

# Step 1: Enable required APIs
echo "📡 Enabling required Google Cloud APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  container.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=$PROJECT_ID

# Step 2: Create Artifact Registry repository
echo "📦 Creating Artifact Registry repository..."
gcloud artifacts repositories create $REPOSITORY \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker repository for Notary API" \
  --project=$PROJECT_ID 2>/dev/null || echo "Repository already exists"

# Step 3: Configure Cloud Build service account permissions
echo "🔐 Configuring Cloud Build service account..."
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant permissions to Cloud Build service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$CLOUD_BUILD_SA \
  --role=roles/artifactregistry.writer \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$CLOUD_BUILD_SA \
  --role=roles/run.admin \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$CLOUD_BUILD_SA \
  --role=roles/iam.serviceAccountUser \
  --project=$PROJECT_ID

# Step 4: Set up Cloud Build GitHub trigger
echo "🔗 Connecting GitHub repository..."
echo "Note: You'll need to authenticate with GitHub in the Cloud Console."
echo "Go to: Cloud Build > Triggers > Connect Repository"
echo "Repository: $GH_REPO"

# Step 5: Display next steps
echo ""
echo "✅ Setup Complete!"
echo ""
echo "Next Steps:"
echo "1. Update cloudbuild.yaml with your actual values"
echo "2. Push code to main branch to trigger builds"
echo "3. View build logs: gcloud builds log --stream=true <BUILD_ID>"
echo "4. View images: gcloud artifacts docker images list $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY"
echo ""
echo "To manually trigger a build:"
echo "  gcloud builds submit --config=cloudbuild.yaml"
echo ""
echo "To deploy to Cloud Run:"
echo "  gcloud run deploy notary-api \\"
echo "    --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest \\"
echo "    --region=$REGION \\"
echo "    --platform=managed"
echo ""
