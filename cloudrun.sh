#!/usr/bin/env bash
set -euo pipefail
: "${GCP_PROJECT:?Set GCP_PROJECT}" 
: "${ADMIN_KEY:?Set ADMIN_KEY}"
gcloud builds submit --tag "gcr.io/${GCP_PROJECT}/ortho-course-api" .
gcloud run deploy ortho-course-api \
  --image "gcr.io/${GCP_PROJECT}/ortho-course-api" \
  --region europe-west2 --platform managed --allow-unauthenticated \
  --set-env-vars "ADMIN_KEY=${ADMIN_KEY},DATABASE_PATH=/tmp/courses.db"
