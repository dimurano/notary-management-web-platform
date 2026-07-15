#!/bin/bash
# Quick start script for deploying Notary API to GCP
# Run this locally on your machine with gcloud CLI installed

set -e

PROJECT_ID="notary-management-web-platform"
REGION="us-central1"
REPOSITORY="notary-repository"
IMAGE_NAME="notary-api"

echo "🚀 Notary API - GCP Quick Start"
echo "================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check authentication
echo "🔐 Checking authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated. Run: gcloud auth login"
    exit 1
fi

# Set project
echo "📋 Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Step 1: Enable APIs
echo "📡 Enabling required APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  container.googleapis.com \
  --quiet

# Step 2: Create Artifact Registry repository
echo "📦 Setting up Artifact Registry repository..."
if gcloud artifacts repositories describe $REPOSITORY --location=$REGION &> /dev/null; then
    echo "   ✓ Repository $REPOSITORY already exists"
else
    echo "   Creating $REPOSITORY..."
    gcloud artifacts repositories create $REPOSITORY \
      --repository-format=docker \
      --location=$REGION \
      --description="Docker repository for Notary API" \
      --quiet
fi

# Step 3: Configure Docker authentication
echo "🔑 Configuring Docker authentication..."
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

# Step 4: Build and push image
echo "🐳 Building and pushing Docker image..."
docker build \
  -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest \
  -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$(git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
  .

docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest

# Step 5: List images
echo ""
echo "✅ Build and Push Complete!"
echo ""
echo "📸 Available Images:"
gcloud artifacts docker images list $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY

# Step 6: Deployment options
echo ""
echo "🎯 Deployment Options:"
echo ""
echo "1️⃣  Deploy to Cloud Run (Recommended for simple APIs):"
echo "   gcloud run deploy notary-api \\"
echo "     --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest \\"
echo "     --region=$REGION \\"
echo "     --platform=managed \\"
echo "     --allow-unauthenticated"
echo ""
echo "2️⃣  Deploy to GKE (Recommended for production):"
echo "   kubectl apply -f k8s/deployment.yaml"
echo ""
echo "3️⃣  Set up GitHub CI/CD:"
echo "   - Go to: https://console.cloud.google.com/cloud-build/triggers"
echo "   - Connect your GitHub repository"
echo "   - Create trigger pointing to cloudbuild.yaml"
echo ""
echo "📖 For detailed guide: see GCP-DEPLOYMENT.md"
echo ""
