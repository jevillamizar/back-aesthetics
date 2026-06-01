"""
Tests de integración para Tarea 3: Validar aislamiento en endpoints (Option A).

Verifica que:
  - GET /api/doctors/ retorna solo doctores del tenant activo.
  - POST /api/doctors/ crea el doctor en el tenant activo.
  - Token de tenant A usado en tenant B retorna 401.
  - GET /public/team/ retorna solo doctores del tenant activo.
"""
import json

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from clinics.models import Clinic, Domain
from users.models import User


class AdminDoctorsIsolationTests(TenantTestCase):
    """Tests para /api/doctors/ con aislamiento por tenant."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)

        # Crear ADMIN en el tenant principal
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Crear doctores en el tenant principal
        self.doc1 = User.objects.create_user(
            email='doc1@test.com',
            password='Pass1234!',
            role=User.Role.DOCTOR,
            is_active=True,
            first_name='Doctor',
            last_name='One',
        )
        self.doc2 = User.objects.create_user(
            email='doc2@test.com',
            password='Pass1234!',
            role=User.Role.DOCTOR,
            is_active=True,
            first_name='Doctor',
            last_name='Two',
        )

    def _auth_header(self, user: User) -> dict:
        """Genera header Authorization con token válido para el usuario."""
        from backend.auth_views import _make_token
        token = _make_token(user)
        return {'Authorization': f'Bearer {token}'}

    def test_list_doctors_only_shows_current_tenant(self) -> None:
        """GET /api/doctors/ retorna solo doctores del tenant activo."""
        # Crear tenant B con un doctor
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic B',
                slug='clinic-b',
                schema_name='clinic_b_endpoint',
            )
            Domain.objects.create(
                domain='clinic-b.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        with schema_context(tenant_b.schema_name):
            User.objects.create_user(
                email='doc_other@clinicb.com',
                password='Pass1234!',
                role=User.Role.DOCTOR,
                is_active=True,
                first_name='Other',
                last_name='Doctor',
            )

        # Listar doctores en tenant principal
        resp = self.client.get(
            '/api/doctors/',
            headers=self._auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)

        emails = [d['email'] for d in data['doctors']]
        self.assertIn('doc1@test.com', emails)
        self.assertIn('doc2@test.com', emails)
        self.assertNotIn('doc_other@clinicb.com', emails)

    def test_create_doctor_in_current_tenant(self) -> None:
        """POST /api/doctors/ crea el doctor en el tenant activo."""
        resp = self.client.post(
            '/api/doctors/',
            data=json.dumps({
                'email': 'newdoc@test.com',
                'first_name': 'New',
                'last_name': 'Doctor',
            }),
            content_type='application/json',
            headers=self._auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 201)

        # Verificar que existe en el tenant
        self.assertTrue(User.objects.filter(email='newdoc@test.com').exists())

    def test_token_from_other_tenant_returns_401(self) -> None:
        """Token de tenant A usado en tenant B → 401."""
        # Generar token del admin en tenant principal
        from backend.auth_views import _make_token
        token = _make_token(self.admin)

        # Crear tenant B
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic C',
                slug='clinic-c',
                schema_name='clinic_c_token',
            )
            Domain.objects.create(
                domain='clinic-c.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        # Intentar usar token en tenant B
        with schema_context(tenant_b.schema_name):
            from django.test import RequestFactory
            from backend.auth_views import get_auth_user

            factory = RequestFactory()
            request = factory.get('/api/doctors/')
            request.headers = {'Authorization': f'Bearer {token}'}

            user = get_auth_user(request)
            self.assertIsNone(user)


class PublicTeamIsolationTests(TenantTestCase):
    """Tests para /public/team/ con aislamiento por tenant."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)

        # Crear doctores en el tenant principal
        self.doc = User.objects.create_user(
            email='publicdoc@test.com',
            password='Pass1234!',
            role=User.Role.DOCTOR,
            is_active=True,
            first_name='Public',
            last_name='Doctor',
            profession='Medicina Estética',
            specialty='Cirugía Plástica',
            bio='Doctor experto en procedimientos estéticos.',
        )

        # Crear doctor inactivo (no debe aparecer)
        User.objects.create_user(
            email='inactivedoc@test.com',
            password='Pass1234!',
            role=User.Role.DOCTOR,
            is_active=False,
            first_name='Inactive',
            last_name='Doctor',
        )

    def test_public_team_only_shows_current_tenant(self) -> None:
        """GET /public/team/ retorna solo doctores del tenant activo."""
        # Crear tenant B con otro doctor
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Public Clinic B',
                slug='public-clinic-b',
                schema_name='public_clinic_b',
            )
            Domain.objects.create(
                domain='public-b.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        with schema_context(tenant_b.schema_name):
            User.objects.create_user(
                email='otherpublic@clinicb.com',
                password='Pass1234!',
                role=User.Role.DOCTOR,
                is_active=True,
                first_name='Other',
                last_name='Public',
            )

        resp = self.client.get('/public/team/')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)

        emails = [m['id'] for m in data['team']]  # 'id' es el user.id, no email
        # Solo debe haber 1 doctor (el activo del tenant principal)
        self.assertEqual(len(data['team']), 1)
        self.assertEqual(data['team'][0]['first_name'], 'Public')

    def test_public_team_excludes_inactive_doctors(self) -> None:
        """GET /public/team/ no incluye doctores inactivos."""
        resp = self.client.get('/public/team/')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)

        names = [f"{m['first_name']} {m['last_name']}" for m in data['team']]
        self.assertIn('Public Doctor', names)
        self.assertNotIn('Inactive Doctor', names)


# ─── Tarea 4: Múltiples admins por tenant permitidos ──────────────────


class MultipleAdminsPerTenantTests(TenantTestCase):
    """
    Tarea 4 — Verifica que un tenant puede tener múltiples usuarios con rol ADMIN.

    Esto permite:
    - Continuidad operativa (backup si un admin abandona)
    - Escalabilidad (clínicas grandes con múltiples gerentes)
    - Recuperación ante desastres (vacaciones, baja médica)
    """

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)

        # Crear primer admin
        self.admin1 = User.objects.create_user(
            email='admin1@test.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            first_name='Admin',
            last_name='One',
        )

    def _auth_header(self, user: User) -> dict:
        """Genera header Authorization con token válido."""
        from backend.auth_views import _make_token
        token = _make_token(user)
        return {'Authorization': f'Bearer {token}'}

    def test_can_create_second_admin_in_same_tenant(self) -> None:
        """Se puede crear un segundo ADMIN en el mismo tenant."""
        # Crear segundo admin directamente (no via endpoint /api/doctors/ que es solo para doctores)
        admin2 = User.objects.create_user(
            email='admin2@test.com',
            password='Admin5678!',
            role=User.Role.ADMIN,
            is_active=True,
            first_name='Admin',
            last_name='Two',
        )

        # Verificar que ambos admins existen
        admin_count = User.objects.filter(role=User.Role.ADMIN).count()
        self.assertEqual(admin_count, 2)

    def test_multiple_admins_can_authenticate_independently(self) -> None:
        """Múltiples admins pueden autenticarse correctamente."""
        # Crear segundo admin
        admin2 = User.objects.create_user(
            email='admin2@test.com',
            password='Admin5678!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Ambos pueden autenticarse
        from backend.tenant_permissions import TenantAuthBackend
        backend = TenantAuthBackend()

        user1 = backend.authenticate(
            None,
            email='admin1@test.com',
            password='Admin1234!',
        )
        user2 = backend.authenticate(
            None,
            email='admin2@test.com',
            password='Admin5678!',
        )

        self.assertIsNotNone(user1)
        self.assertIsNotNone(user2)
        self.assertEqual(user1.pk, self.admin1.pk)
        self.assertEqual(user2.pk, admin2.pk)

    def test_admin_can_create_doctor_while_other_admin_exists(self) -> None:
        """Un admin puede crear doctores aunque haya otro admin."""
        # Crear segundo admin
        User.objects.create_user(
            email='admin2@test.com',
            password='Admin5678!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Primer admin crea un doctor
        resp = self.client.post(
            '/api/doctors/',
            data=json.dumps({
                'email': 'newdoctor@test.com',
                'first_name': 'New',
                'last_name': 'Doctor',
            }),
            content_type='application/json',
            headers=self._auth_header(self.admin1),
        )
        self.assertEqual(resp.status_code, 201)

        # Verificar que el doctor se creó
        self.assertTrue(User.objects.filter(email='newdoctor@test.com').exists())

    def test_admins_are_isolated_between_tenants(self) -> None:
        """Los admins de tenant A no son visibles en tenant B."""
        # Crear tenant B
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic B Multi',
                slug='clinic-b-multi',
                schema_name='clinic_b_multi',
            )
            Domain.objects.create(
                domain='clinic-b-multi.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        # Tenant B tiene su propio admin
        with schema_context(tenant_b.schema_name):
            admin_b = User.objects.create_user(
                email='admin@clinicb.com',
                password='Admin9999!',
                role=User.Role.ADMIN,
                is_active=True,
            )

        # En tenant principal: solo vemos admin1
        admins_principal = list(User.objects.filter(role=User.Role.ADMIN).values_list('email', flat=True))
        self.assertIn('admin1@test.com', admins_principal)
        self.assertNotIn('admin@clinicb.com', admins_principal)

        # En tenant B: solo vemos su admin
        with schema_context(tenant_b.schema_name):
            admins_b = list(User.objects.filter(role=User.Role.ADMIN).values_list('email', flat=True))
            self.assertIn('admin@clinicb.com', admins_b)
            self.assertNotIn('admin1@test.com', admins_b)
