"""
Tests de IDOR (Insecure Direct Object Reference) para Option A.

Verifica que IDs de usuarios de otros tenants no sean accesibles.
"""
import json

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from clinics.models import Clinic, Domain
from users.models import User
from patients.models import Patient


class IDORCrossTenantUserTests(TenantTestCase):
    """Tests IDOR: intentar acceder a usuarios de otros tenants via ID."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)

        # Crear admin en tenant principal
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Crear doctor en tenant principal (ID conocido)
        self.doctor_principal = User.objects.create_user(
            email='doctor@test.com',
            password='Pass1234!',
            role=User.Role.DOCTOR,
            is_active=True,
            first_name='Doctor',
            last_name='Principal',
        )
        self.doctor_principal_id = self.doctor_principal.id

    def _auth_header(self, user: User) -> dict:
        """Genera header Authorization con token válido."""
        from backend.auth_views import _make_token
        token = _make_token(user)
        return {'Authorization': f'Bearer {token}'}

    def test_doctor_id_from_other_tenant_not_accessible(self) -> None:
        """
        IDOR Test: Un doctor creado en tenant B NO debe ser accesible
        desde tenant A aunque se conozca su ID.
        """
        # Crear tenant B con su propio doctor
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic B IDOR',
                slug='clinic-b-idor',
                schema_name='clinic_b_idor_test',
            )
            Domain.objects.create(
                domain='clinic-b-idor.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        with schema_context(tenant_b.schema_name):
            doctor_b = User.objects.create_user(
                email='doctor_b@test.com',
                password='Pass1234!',
                role=User.Role.DOCTOR,
                is_active=True,
            )
            doctor_b_id = doctor_b.id

        # Intentar acceder al doctor de tenant B desde tenant principal
        from django.db import connection
        with schema_context(self.tenant.schema_name):
            current_schema = connection.schema_name
            all_users = list(User.objects.values('id', 'email', 'role'))

            # Intentar obtener el doctor - esto NO debería funcionar
            try:
                doctor_found = User.objects.get(id=doctor_b_id)
                self.fail(
                    f"IDOR VULNERABILIDAD: Doctor de otro tenant es accesible!\n"
                    f"Schema actual: {current_schema}\n"
                    f"Buscando ID: {doctor_b_id} (creado en {tenant_b.schema_name})\n"
                    f"Doctor encontrado: {doctor_found.email}\n"
                    f"Usuarios en este schema: {all_users}"
                )
            except User.DoesNotExist:
                pass  # Expected - el doctor no debe existir en este schema

    def test_medical_record_creation_with_other_tenant_doctor_fails(self) -> None:
        """
        IDOR Test: Intentar crear medical record con doctor_id de otro tenant.
        Debe retornar 404 (Doctor not found).
        """
        # Crear patient en tenant principal
        patient = Patient.objects.create(
            first_name='Test',
            last_name='Patient',
            email='patient@test.com',
            phone='123456',
        )

        # Crear tenant B con doctor
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic B Medical',
                slug='clinic-b-medical',
                schema_name='clinic_b_medical_test',
            )
            Domain.objects.create(
                domain='clinic-b-medical.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        with schema_context(tenant_b.schema_name):
            doctor_b = User.objects.create_user(
                email='doctor_b_medical@test.com',
                password='Pass1234!',
                role=User.Role.DOCTOR,
                is_active=True,
            )
            doctor_b_id = doctor_b.id

        # Intentar crear medical record usando ID de doctor de otro tenant
        resp = self.client.post(
            '/api/medical-records/',
            data=json.dumps({
                'patient_id': patient.id,
                'doctor_id': doctor_b_id,  # ID de doctor en OTRO tenant
                'chief_complaint': 'Test',
            }),
            content_type='application/json',
            headers=self._auth_header(self.admin),
        )

        # Debe retornar 400 (Doctor not found)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertIn('Doctor not found', data['detail'])
