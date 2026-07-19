# Cloud Run Deployment - Fixed Configuration

## Issue Resolved
The previous deployment failed because:
1. ✅ Database initialization was blocking app startup
2. ✅ Health check timeout was too aggressive
3. ✅ RTF file encoding issues (models.py was in RTF format)

All fixed in this version.

---

## Deployment Steps

### Option 1: One-Command Deployment (Recommended)
```bash
chmod +x deploy-cloud-run.sh
./deploy-cloud-run.sh
```

### Option 2: Manual Deployment
```bash
# 1. Set variables
export PROJECT_ID="notary-management-web-platform"
export REGION="us-central1"
export IMAGE_URL="us-central1-docker.pkg.dev/${PROJECT_ID}/notary-repository/notary-api:latest"

# 2. Push image (if not already pushed)
docker push $IMAGE_URL

# 3. Deploy to Cloud Run
gcloud run deploy notary-api \
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
  --set-cloudsql-instances=notary-management-web-platform:us-central1:notary-db-instance
```

---

## What Changed

### main.py
- ✅ Database connection no longer blocks startup
- ✅ Tables created in startup event (non-blocking)
- ✅ Health check returns immediately
- ✅ 503 error if database unavailable (but app still starts)
- ✅ Better error logging

### models.py
- ✅ Converted from RTF to plain Python
- ✅ Database indexes optimized

### Dockerfile
- ✅ Entrypoint script for better startup handling
- ✅ Removed aggressive health check (Cloud Run manages it)
- ✅ NullPool connection mode for Cloud Run

---

## Testing Locally

```bash
# Build image
docker build -t notary-api:latest .

# Run with PostgreSQL connection string
docker run -d --name test-notary \
  -p 8080:8080 \
  -e DATABASE_URL="postgresql://user:pass@localhost/db" \
  notary-api:latest

# Health check
curl http://localhost:8080/api/health

# Stop
docker stop test-notary
```

---

## Verification After Deployment

```bash
# Get service URL
gcloud run services describe notary-api --region=us-central1 --format="value(status.url)"

# Test health endpoint
curl https://<SERVICE_URL>/api/health

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=notary-api" --limit=50
```

---

## Troubleshooting

**Still failing to start?**
Check logs with detailed filter:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=notary-api AND severity=ERROR" --limit=20
```

**Database connection issues?**
Health check returns: `"database": "unavailable"` if connection fails
- Verify Cloud SQL instance is running
- Verify `--set-cloudsql-instances` flag is set correctly
- Ensure service account has Cloud SQL Client role

**Port issues?**
Cloud Run expects the app to listen on `$PORT` (8080 in this case)
- Verify Dockerfile exposes port 8080
- Verify uvicorn binds to 0.0.0.0:8080

---

## Database URL Formats

### Development (SQLite)
```
DATABASE_URL="sqlite:///./data/notary_journal.db"
```

### Production (Cloud SQL PostgreSQL)
```
DATABASE_URL="postgresql+pg8000://user:password@cloudsql-instance/database"
```
With Cloud SQL proxy:
```
DATABASE_URL="postgresql://user:password@cloudsql-proxy:5432/database"
```

---

## Next Steps After Successful Deployment

1. **Add authentication/authorization** - Currently `--allow-unauthenticated`
2. **Set custom domain** - Use Cloud Run custom domains feature
3. **Add monitoring** - Set up Cloud Monitoring dashboards
4. **Configure database backups** - Cloud SQL automated backups
5. **Enable VPC** - Isolate service network access
