#!/bin/bash
# Quick reference: Notary API deployment commands

echo "🚀 Notary API - Cloud Run Deployment Quick Reference"
echo "====================================================="
echo ""

SERVICE_NAME="notary-api"
REGION="us-central1"
PROJECT_ID="notary-management-web-platform"

echo "📍 Service Details:"
echo "  Project: $PROJECT_ID"
echo "  Service: $SERVICE_NAME"
echo "  Region: $REGION"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" 2>/dev/null)

if [ -z "$SERVICE_URL" ]; then
    echo "❌ Service not found. Deployment may still be in progress."
    echo ""
    echo "Check status with:"
    echo "  gcloud run services describe $SERVICE_NAME --region=$REGION"
    exit 1
fi

echo "✅ Service URL: $SERVICE_URL"
echo ""

echo "📊 Quick Actions:"
echo ""
echo "1. Test Health Endpoint:"
echo "   curl $SERVICE_URL/api/health"
echo ""
echo "2. View API Documentation:"
echo "   $SERVICE_URL/docs"
echo ""
echo "3. View Logs (last 50):"
echo "   gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" --limit=50"
echo ""
echo "4. Stream Logs (real-time):"
echo "   gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" --follow"
echo ""
echo "5. Check Service Status:"
echo "   gcloud run services describe $SERVICE_NAME --region=$REGION"
echo ""
echo "6. Update Environment Variables:"
echo "   gcloud run services update $SERVICE_NAME --region=$REGION --set-env-vars KEY=VALUE"
echo ""
echo "7. Scale Service:"
echo "   gcloud run services update $SERVICE_NAME --region=$REGION --min-instances=1 --max-instances=50"
echo ""
echo "8. Disable Public Access:"
echo "   gcloud run services update-iam-policy $SERVICE_NAME --region=$REGION --no-allow-unauthenticated"
echo ""
echo "9. View Metrics:"
echo "   gcloud monitoring time-series list --filter='metric.type=\"run.googleapis.com/request_count\"'"
echo ""
echo "10. Delete Service (careful!):"
echo "    gcloud run services delete $SERVICE_NAME --region=$REGION"
echo ""

# Test health endpoint
echo "🏥 Testing health endpoint..."
HEALTH=$(curl -s "$SERVICE_URL/api/health" | grep -o '"status":"ok"' || echo "failed")

if [ "$HEALTH" = '"status":"ok"' ]; then
    echo "✅ Service is healthy!"
else
    echo "⚠️  Health check returned: $(curl -s "$SERVICE_URL/api/health")"
fi

echo ""
echo "📚 Documentation: See POST-DEPLOYMENT.md for detailed verification steps"
