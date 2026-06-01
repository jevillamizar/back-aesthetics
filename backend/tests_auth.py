"""
Tests para TenantAuthBackend — Tarea 0: Fix del login roto.

Bugs que demuestran los tests:
  Bug 1 — auth_login pasa email= como kwarg, pero el backend espera username=.
           username=None → retorna None sin autenticar.
  Bug 2 — En schema de tenant exige is_staff=True.
           Los usuarios ADMIN/DOCTOR no tienen is_staff, solo role=ADMIN/DOCTOR.
"""
import json

from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from backend.tenant_permissions import TenantAuthBackend
from users.models import User


# ─── Tests unitarios del backend ────────────────────────────────────


class TenantAuthBackendBug1Tests(TenantTestCase):
    """Bug 1: el backend ignora el kwarg email= que usa auth_login."""

    def setUp(self) -> None:
        self.backend = TenantAuthBackend()
        self.factory = RequestFactory()
        self.request = self.factory.post('/api/auth/login/')

        self.admin = User.objects.create_user(
            email='admin@testclinic.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=False,
        )

    def test_backend_con_email_kwarg_retorna_usuario(self) -> None:
        """
        auth_login llama authenticate(request, email=..., password=...).
        Con código actual: username=None → retorna None (Bug 1).
        Con fix: acepta email kwarg → retorna usuario.
        """
        result = self.backend.authenticate(
            self.request,
            email='admin@testclinic.com',
            password='Admin1234!',
        )
        self.assertIsNotNone(result, 'Bug 1: el backend devuelve None porque username=None')
        self.assertEqual(result.pk, self.admin.pk)


class TenantAuthBackendBug2Tests(TenantTestCase):
    """Bug 2: el backend exige is_staff=True en lugar de role=ADMIN/DOCTOR."""

    def setUp(self) -> None:
        self.backend = TenantAuthBackend()
        self.factory = RequestFactory()
        self.request = self.factory.post('/api/auth/login/')

        # Usuarios como los creados manualmente en Cloud SQL:
        # tienen role pero NO is_staff (is_staff=False es el default de Django)
        self.admin = User.objects.create_user(
            email='admin@testclinic.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=False,
        )
        self.doctor = User.objects.create_user(
            email='doctor@testclinic.com',
            password='Doctor1234!',
            role=User.Role.DOCTOR,
            is_active=True,
            is_staff=False,
        )

    def test_admin_sin_is_staff_puede_autenticarse(self) -> None:
        """
        ADMIN con is_staff=False en schema de tenant debe poder autenticarse.
        Con código actual: not user.is_staff → retorna None (Bug 2).
        Con fix: chequea role=ADMIN → retorna usuario.
        """
        result = self.backend.authenticate(
            self.request,
            username='admin@testclinic.com',
            password='Admin1234!',
        )
        self.assertIsNotNone(result, 'Bug 2: ADMIN sin is_staff es rechazado')
        self.assertEqual(result.role, User.Role.ADMIN)

    def test_doctor_sin_is_staff_puede_autenticarse(self) -> None:
        """
        DOCTOR con is_staff=False en schema de tenant debe poder autenticarse.
        Con código actual: not user.is_staff → retorna None (Bug 2).
        """
        result = self.backend.authenticate(
            self.request,
            username='doctor@testclinic.com',
            password='Doctor1234!',
        )
        self.assertIsNotNone(result, 'Bug 2: DOCTOR sin is_staff es rechazado')
        self.assertEqual(result.role, User.Role.DOCTOR)


# ─── Tests de comportamiento correcto (deben pasar antes y después del fix) ─


class TenantAuthBackendComportamientoTests(TenantTestCase):
    """Comportamiento que debe mantenerse tanto en código actual como con el fix."""

    def setUp(self) -> None:
        self.backend = TenantAuthBackend()
        self.factory = RequestFactory()
        self.request = self.factory.post('/api/auth/login/')

        self.admin = User.objects.create_user(
            email='admin@testclinic.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=False,
        )
        self.client_user = User.objects.create_user(
            email='client@testclinic.com',
            password='Client1234!',
            role=User.Role.CLIENT,
            is_active=True,
            is_staff=False,
        )

    def test_contrasena_incorrecta_retorna_none(self) -> None:
        """Contraseña incorrecta → None siempre."""
        result = self.backend.authenticate(
            self.request,
            email='admin@testclinic.com',
            password='WrongPassword!',
        )
        self.assertIsNone(result)

    def test_email_inexistente_retorna_none(self) -> None:
        """Email que no existe → None siempre."""
        result = self.backend.authenticate(
            self.request,
            email='nobody@testclinic.com',
            password='Admin1234!',
        )
        self.assertIsNone(result)

    def test_usuario_inactivo_retorna_none(self) -> None:
        """is_active=False → None siempre."""
        self.admin.is_active = False
        self.admin.save()
        result = self.backend.authenticate(
            self.request,
            email='admin@testclinic.com',
            password='Admin1234!',
        )
        self.assertIsNone(result)

    def test_role_client_retorna_none(self) -> None:
        """role=CLIENT no puede autenticarse vía API (solo ADMIN y DOCTOR)."""
        result = self.backend.authenticate(
            self.request,
            email='client@testclinic.com',
            password='Client1234!',
        )
        self.assertIsNone(result)

    def test_sin_email_ni_username_retorna_none(self) -> None:
        """Sin credenciales → None siempre."""
        result = self.backend.authenticate(self.request, password='Admin1234!')
        self.assertIsNone(result)


# ─── Tests de integración del endpoint /api/auth/login/ ─────────────


class LoginEndpointIntegrationTests(TenantTestCase):
    """Tests de integración para POST /api/auth/login/ — Tarea 0."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)

        # Simula exactamente los usuarios creados manualmente en Cloud SQL:
        # tienen role=ADMIN pero is_staff=False
        self.admin = User.objects.create_user(
            email='admin@testclinic.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=False,
        )

    def test_login_exitoso_admin_sin_is_staff(self) -> None:
        """
        POST /api/auth/login/ con ADMIN (is_staff=False) → 200 + token.
        Replica el escenario exacto de producción (usuarios creados manualmente).
        """
        resp = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@testclinic.com', 'password': 'Admin1234!'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('token', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['role'], 'ADMIN')
        self.assertEqual(data['user']['email'], 'admin@testclinic.com')

    def test_login_falla_contrasena_incorrecta(self) -> None:
        """POST /api/auth/login/ contraseña incorrecta → 401."""
        resp = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@testclinic.com', 'password': 'wrong'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_falla_email_inexistente(self) -> None:
        """POST /api/auth/login/ email desconocido → 401."""
        resp = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'nobody@x.com', 'password': 'Admin1234!'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_falla_usuario_inactivo(self) -> None:
        """
        POST /api/auth/login/ usuario inactivo → 401.
        Todos los backends filtran is_active=False → authenticate() retorna None
        → auth_login devuelve 401 (el check de 403 post-authenticate nunca se alcanza).
        """
        self.admin.is_active = False
        self.admin.save()
        resp = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@testclinic.com', 'password': 'Admin1234!'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)
