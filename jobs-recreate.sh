#!/bin/bash
# Recrear jobs de migración con variables de entorno y Cloud SQL
# Uso: ./jobs-recreate.sh
# Requiere: gcloud autenticado, permisos en Cloud Run y Cloud SQL

set -e  # Salir en cualquier error

PROJECT_ID=aestheticsaas-495821
REGION=us-central1
IMAGE=us-central1-docker.pkg.dev/${PROJECT_ID}/aesthetics-repo/backend:latest

echo "Obteniendo secrets de Secret Manager..."
SECRET_KEY=$(gcloud secrets versions access latest --secret=django-secret-key --project=${PROJECT_ID})
POSTGRES_PASSWORD=$(gcloud secrets versions access latest --secret=db-password --project=${PROJECT_ID})

# Eliminar jobs existentes
echo "Eliminando jobs antiguos..."
gcloud run jobs delete migrate-schemas --region=${REGION} --quiet 2>/dev/null || true
gcloud run jobs delete migrate-users --region=${REGION} --quiet 2>/dev/null || true
gcloud run jobs delete create-support-user --region=${REGION} --quiet 2>/dev/null || true

# Crear job: migrate-schemas
echo "Creando job migrate-schemas..."
gcloud run jobs create migrate-schemas \
  --image=${IMAGE} \
  --region=${REGION} \
  --command="python" \
  --args="manage.py,migrate_schemas" \
  --set-env-vars="POSTGRES_DB=app_db,POSTGRES_USER=app,POSTGRES_HOST=/cloudsql/aestheticsaas-495821:us-central1:aesthetics-db,POSTGRES_PORT=5432,DEBUG=False,TENANT_BASE_DOMAIN=aesthssco.com,ALLOWED_HOSTS=.aesthssco.com" \
  --set-env-vars="SECRET_KEY=${SECRET_KEY},POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
  --set-cloudsql-instances=aestheticsaas-495821:us-central1:aesthetics-db

# Crear job: migrate-users
echo "Creando job migrate-users..."
gcloud run jobs create migrate-users \
  --image=${IMAGE} \
  --region=${REGION} \
  --command="python" \
  --args="manage.py,migrate_users_to_tenants,--mapping=admin@demo-clinic.com:demo_clinic,--mapping=nathalyp@unicauca.edu.co:dra_nathaly_pino" \
  --set-env-vars="POSTGRES_DB=app_db,POSTGRES_USER=app,POSTGRES_HOST=/cloudsql/aestheticsaas-495821:us-central1:aesthetics-db,POSTGRES_PORT=5432,DEBUG=False,TENANT_BASE_DOMAIN=aesthssco.com,ALLOWED_HOSTS=.aesthssco.com" \
  --set-env-vars="SECRET_KEY=${SECRET_KEY},POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
  --set-cloudsql-instances=aestheticsaas-495821:us-central1:aesthetics-db

# Crear job: create-support-user
echo "Creando job create-support-user..."
gcloud run jobs create create-support-user \
  --image=${IMAGE} \
  --region=${REGION} \
  --command="python" \
  --args="manage.py,create_support_user_all_tenants,--email=support@aesthetics.com,--password=SoporteAesthetics2026!" \
  --set-env-vars="POSTGRES_DB=app_db,POSTGRES_USER=app,POSTGRES_HOST=/cloudsql/aestheticsaas-495821:us-central1:aesthetics-db,POSTGRES_PORT=5432,DEBUG=False,TENANT_BASE_DOMAIN=aesthssco.com,ALLOWED_HOSTS=.aesthssco.com" \
  --set-env-vars="SECRET_KEY=${SECRET_KEY},POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
  --set-cloudsql-instances=aestheticsaas-495821:us-central1:aesthetics-db

echo ""
echo "✅ Jobs creados exitosamente!"
echo ""
echo "Ejecutar en orden:"
echo "  gcloud run jobs execute migrate-schemas --region=${REGION}"
echo "  gcloud run jobs execute migrate-users --region=${REGION}"
echo "  gcloud run jobs execute create-support-user --region=${REGION}"
