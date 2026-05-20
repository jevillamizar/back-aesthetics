import json

from django.core import signing
from django.test import TestCase
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from clinics.models import Clinic
from users.models import User


class ClinicModuleFieldsTest(TestCase):
    """T1 — Verifica que Clinic tiene los flags de funcionalidades."""

    def test_enable_medical_history_field_exists(self) -> None:
        """El modelo Clinic debe tener el campo enable_medical_history."""
        field = Clinic._meta.get_field('enable_medical_history')
        self.assertIsNotNone(field)
        self.assertEqual(field.get_internal_type(), 'BooleanField')

    def test_enable_medical_history_defaults_to_true(self) -> None:
        """El default de enable_medical_history debe ser True."""
        field = Clinic._meta.get_field('enable_medical_history')
        self.assertTrue(field.default)

    def test_enable_consent_field_exists(self) -> None:
        """El modelo Clinic debe tener el campo enable_consent."""
        field = Clinic._meta.get_field('enable_consent')
        self.assertIsNotNone(field)
        self.assertEqual(field.get_internal_type(), 'BooleanField')

    def test_enable_consent_defaults_to_true(self) -> None:
        """El default de enable_consent debe ser True."""
        field = Clinic._meta.get_field('enable_consent')
        self.assertTrue(field.default)

    def test_str_unchanged(self) -> None:
        """__str__ sigue retornando el nombre de la clínica sin cambios."""
        clinic = Clinic(name='Test Clinic', slug='test', schema_name='test')
        self.assertEqual(str(clinic), 'Test Clinic')


class ClinicModuleFlagsAPITest(TenantTestCase):
    """T7 — Verifica que GET/PUT /api/clinic/ expone y persiste los flags."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def test_get_clinic_returns_enable_medical_history(self) -> None:
        """GET /api/clinic/ retorna enable_medical_history."""
        resp = self.client.get('/api/clinic/', **self.auth)
        data = json.loads(resp.content)
        self.assertIn('enable_medical_history', data['clinic'])
        self.assertTrue(data['clinic']['enable_medical_history'])

    def test_get_clinic_returns_enable_consent(self) -> None:
        """GET /api/clinic/ retorna enable_consent."""
        resp = self.client.get('/api/clinic/', **self.auth)
        data = json.loads(resp.content)
        self.assertIn('enable_consent', data['clinic'])
        self.assertTrue(data['clinic']['enable_consent'])

    def test_put_clinic_updates_enable_medical_history(self) -> None:
        """PUT /api/clinic/ actualiza enable_medical_history."""
        resp = self.client.put(
            '/api/clinic/',
            json.dumps({'enable_medical_history': False}),
            content_type='application/json', **self.auth,
        )
        data = json.loads(resp.content)
        self.assertFalse(data['clinic']['enable_medical_history'])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.enable_medical_history)

    def test_put_clinic_updates_enable_consent(self) -> None:
        """PUT /api/clinic/ actualiza enable_consent."""
        resp = self.client.put(
            '/api/clinic/',
            json.dumps({'enable_consent': False}),
            content_type='application/json', **self.auth,
        )
        data = json.loads(resp.content)
        self.assertFalse(data['clinic']['enable_consent'])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.enable_consent)

    def test_put_clinic_forces_consent_off_when_hc_disabled(self) -> None:
        """PUT /api/clinic/ fuerza enable_consent=False si enable_medical_history=False."""
        resp = self.client.put(
            '/api/clinic/',
            json.dumps({'enable_medical_history': False, 'enable_consent': True}),
            content_type='application/json', **self.auth,
        )
        data = json.loads(resp.content)
        self.assertFalse(data['clinic']['enable_medical_history'])
        self.assertFalse(data['clinic']['enable_consent'])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.enable_consent)

    def test_get_clinic_accessible_by_doctor(self) -> None:
        """GET /api/clinic/ debe ser accesible para DOCTOR (lectura de config)."""
        doctor = User.objects.create_user(
            email='doc@test.com', password='Test1234!', role='DOCTOR',
        )
        token = signing.dumps({'uid': doctor.pk}, salt='auth-token')
        resp = self.client.get('/api/clinic/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('enable_medical_history', data['clinic'])

    def test_put_clinic_forbidden_for_doctor(self) -> None:
        """PUT /api/clinic/ debe seguir restringido a ADMIN."""
        doctor = User.objects.create_user(
            email='doc2@test.com', password='Test1234!', role='DOCTOR',
        )
        token = signing.dumps({'uid': doctor.pk}, salt='auth-token')
        resp = self.client.put(
            '/api/clinic/',
            json.dumps({'enable_medical_history': False}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(resp.status_code, 403)

    def test_get_clinic_forbidden_for_client(self) -> None:
        """GET /api/clinic/ debe estar bloqueado para CLIENT."""
        client_user = User.objects.create_user(
            email='client@test.com', password='Test1234!', role='CLIENT',
        )
        token = signing.dumps({'uid': client_user.pk}, salt='auth-token')
        resp = self.client.get('/api/clinic/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 403)
