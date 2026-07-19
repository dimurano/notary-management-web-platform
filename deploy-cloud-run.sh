#!/bin/bash
# Deploy to Cloud Run with fixed configuration

set -e

PROJECT_ID="notary-management-web-platform"
REGION="us-central1"
SERVICE_NAME="notary-api"
IMAGE_URL="us-central1-docker.pkg.dev/${PROJECT_ID}/notary-repository/${SERVICE_NAME}:latest"

echo "🚀 Deploying Notary API to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Image: $IMAGE_URL"
echo ""

# Push to Artifact Registry first (if Docker is available locally)
if command -v docker &> /dev/null; then
    echo "📦 Pushing image to Artifact Registry..."
    docker push $IMAGE_URL
fi

# Deploy to Cloud Run with correct settings
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE_URL \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --timeout=3600 \
  --max-instances=20 \
  --set-env-vars="ENVIRONMENT=production" \
  --set-cloudsql-instances=notary-management-web-platform:us-central1:notary-db-instance \
  --project=$PROJECT_ID \
  --quiet

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Service URL:"
gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" --project=$PROJECT_ID
echo ""
echo "View logs:"
echo "  gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" --limit=50"
