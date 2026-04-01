#!/usr/bin/env python
"""
Script to configure localhost domain for public schema access
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from clinics.models import Clinic, Domain
from django.db import connection

# Set to public schema
connection.set_schema_to_public()

# Get or create public tenant
public_tenant = Clinic.objects.filter(schema_name='public').first()
if not public_tenant:
    print("Creating public tenant...")
    public_tenant = Clinic.objects.create(
        schema_name='public',
        name='Public Schema',
        slug='public'
    )
    print(f"Created: {public_tenant}")

# Create localhost domain
domain, created = Domain.objects.get_or_create(
    domain='localhost',
    defaults={
        'tenant': public_tenant,
        'is_primary': True
    }
)

if created:
    print(f"Created domain: {domain.domain} -> {public_tenant.name}")
else:
    print(f"Domain already exists: {domain.domain} -> {public_tenant.name}")

print("\n✅ localhost is now configured for public schema access")
print("You can now access: http://localhost:8000/admin/")
