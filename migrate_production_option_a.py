#!/usr/bin/env python
"""
Script de migración a producción Option A (users por tenant).
Ejecutar en Cloud Run o entorno con acceso a Cloud SQL.

Uso:
  python manage.py shell < migrate_production_option_a.py
"""
import sys
from django_tenants.utils import schema_context
from django.db import connection
from clinics.models import Clinic
from users.models import User

SUPPORT_EMAIL = 'support@aesthetics.com'
SUPPORT_PASSWORD = 'SoporteAesthetics2026!'

print("=" * 60)
print("MIGRACION OPTION A - Users por Tenant")
print("=" * 60)

# =============================================================================
# PASO 1: Verificar estado inicial
# =============================================================================
print("\n📋 PASO 1: Verificando estado inicial...")

with schema_context('public'):
    public_users = list(User.objects.values('email', 'role', 'is_active'))
    print(f"\nUsuarios en public.users_user: {len(public_users)}")
    for u in public_users:
        print(f"  - {u['email']} | role: {u['role']} | active: {u['is_active']}")

with schema_context('public'):
    clinics = list(Clinic.objects.exclude(schema_name='public').values('name', 'schema_name'))
    print(f"\nTenants encontrados: {len(clinics)}")
    for c in clinics:
        print(f"  - {c['name']}: schema={c['schema_name']}")

# =============================================================================
# PASO 2: Verificar tablas users_user en cada tenant (post-migrate_schemas)
# =============================================================================
print("\n📋 PASO 2: Verificando tablas users_user en tenants...")

cursor = connection.cursor()
for clinic in clinics:
    schema = clinic['schema_name']
    try:
        cursor.execute(f"SET search_path TO {schema}; SELECT COUNT(*) FROM users_user;")
        count = cursor.fetchone()[0]
        print(f"  {schema}.users_user: {count} registros")
    except Exception as e:
        print(f"  ❌ {schema}.users_user: ERROR - {e}")
        print("     Ejecutar: python manage.py migrate_schemas")
        sys.exit(1)

# =============================================================================
# PASO 3: Migrar usuarios de public a sus tenants
# =============================================================================
print("\n📋 PASO 3: Migrando usuarios de public a tenants...")

# Mapeo email -> schema (ajustar según corresponda)
USER_TENANT_MAPPING = {
    'admin@demo-clinic.com': 'demo_clinic',
    'nathalyp@unicauca.edu.co': 'unicauca',
}

migrated = 0
skipped = 0

for user_data in public_users:
    email = user_data['email']
    target_schema = USER_TENANT_MAPPING.get(email)

    if not target_schema:
        print(f"  ⚠️  {email}: no tiene tenant asignado en mapping, omitiendo")
        skipped += 1
        continue

    # Verificar que el tenant existe
    if not Clinic.objects.filter(schema_name=target_schema).exists():
        print(f"  ❌ {email}: tenant {target_schema} no existe")
        skipped += 1
        continue

    # Verificar si ya existe en el tenant destino
    with schema_context(target_schema):
        if User.objects.filter(email=email).exists():
            print(f"  ⚠️  {email}: ya existe en {target_schema}, omitiendo")
            skipped += 1
            continue

    # Copiar usuario
    with schema_context('public'):
        try:
            source_user = User.objects.get(email=email)
        except User.DoesNotExist:
            print(f"  ❌ {email}: no encontrado en public")
            skipped += 1
            continue

    with schema_context(target_schema):
        User.objects.create_user(
            email=source_user.email,
            password='temp_password_will_be_replaced',  # No usamos la password, se copia el hash manualmente
            role=source_user.role,
            first_name=source_user.first_name,
            last_name=source_user.last_name,
            is_active=source_user.is_active,
            is_staff=source_user.is_staff,
        )

        # Actualizar con el hash de password original
        new_user = User.objects.get(email=email)
        with schema_context('public'):
            original = User.objects.get(email=email)
            new_user.password = original.password  # Copiar hash directamente
            new_user.save(update_fields=['password'])

        print(f"  ✅ {email}: migrado a {target_schema}")
        migrated += 1

print(f"\nMigración completada: {migrated} migrados, {skipped} omitidos")

# =============================================================================
# PASO 4: Crear usuario de soporte en todos los tenants
# =============================================================================
print("\n📋 PASO 4: Creando usuario de soporte...")

support_created = 0
support_skipped = 0

for clinic in clinics:
    schema = clinic['schema_name']

    with schema_context(schema):
        if User.objects.filter(email=SUPPORT_EMAIL).exists():
            print(f"  ⚠️  {schema}: {SUPPORT_EMAIL} ya existe")
            support_skipped += 1
            continue

        User.objects.create_user(
            email=SUPPORT_EMAIL,
            password=SUPPORT_PASSWORD,
            role=User.Role.ADMIN,
            first_name='Soporte',
            last_name='Tecnico',
            is_active=True,
            is_staff=True,
        )
        print(f"  ✅ {schema}: {SUPPORT_EMAIL} creado")
        support_created += 1

print(f"\nSoporte: {support_created} creados, {support_skipped} ya existentes")

# =============================================================================
# PASO 5: Verificación final
# =============================================================================
print("\n📋 PASO 5: Verificación final...")

for clinic in clinics:
    schema = clinic['schema_name']
    with schema_context(schema):
        users = list(User.objects.values('email', 'role'))
        print(f"\n  {schema}: {len(users)} usuarios")
        for u in users:
            print(f"    - {u['email']} ({u['role']})")

print("\n" + "=" * 60)
print("✅ MIGRACION COMPLETADA")
print("=" * 60)
print("\nPróximos pasos:")
print("  1. Verificar login funciona en cada tenant")
print("  2. Verificar token de tenant A no funciona en tenant B")
print("  3. Verificar /public/team/ solo muestra doctores del tenant")
