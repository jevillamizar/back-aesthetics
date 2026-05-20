import json

from django.core import signing
from django.test import TestCase
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from treatments.models import Treatment
from users.models import User


class TreatmentRequiresConsentFieldTest(TestCase):
    """T3 — Verifica metadata del campo requires_consent en Treatment."""

    def test_requires_consent_field_exists(self) -> None:
        """El modelo Treatment debe tener el campo requires_consent."""
        field = Treatment._meta.get_field('requires_consent')
        self.assertIsNotNone(field)
        self.assertEqual(field.get_internal_type(), 'BooleanField')

    def test_requires_consent_defaults_to_false(self) -> None:
        """El default de requires_consent debe ser False."""
        field = Treatment._meta.get_field('requires_consent')
        self.assertFalse(field.default)


class TreatmentRequiresConsentPersistTest(TenantTestCase):
    """T3 — Verifica persistencia de requires_consent (requiere tenant schema)."""

    def test_requires_consent_persists_true(self) -> None:
        """Un tratamiento con requires_consent=True persiste correctamente."""
        t = Treatment.objects.create(
            name='Test Treatment',
            slug='test-treatment',
            requires_consent=True,
        )
        t.refresh_from_db()
        self.assertTrue(t.requires_consent)

    def test_requires_consent_persists_false(self) -> None:
        """Un tratamiento sin requires_consent persiste como False."""
        t = Treatment.objects.create(
            name='Test Treatment 2',
            slug='test-treatment-2',
        )
        t.refresh_from_db()
        self.assertFalse(t.requires_consent)


class TreatmentRequiresConsentAPITest(TenantTestCase):
    """T5/T6 — Verifica que la API expone y persiste requires_consent."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    # ── T5: GET retorna requires_consent ──

    def test_list_includes_requires_consent(self) -> None:
        """GET /api/treatments/ retorna requires_consent en cada tratamiento."""
        Treatment.objects.create(name='T1', slug='t1', requires_consent=True)
        Treatment.objects.create(name='T2', slug='t2', requires_consent=False)
        resp = self.client.get('/api/treatments/', **self.auth)
        data = json.loads(resp.content)
        treatments = data['treatments']
        self.assertEqual(len(treatments), 2)
        by_name = {t['name']: t for t in treatments}
        self.assertTrue(by_name['T1']['requires_consent'])
        self.assertFalse(by_name['T2']['requires_consent'])

    def test_detail_includes_requires_consent(self) -> None:
        """GET /api/treatments/:id/ retorna requires_consent."""
        t = Treatment.objects.create(name='T1', slug='t1', requires_consent=True)
        resp = self.client.get(f'/api/treatments/{t.id}/', **self.auth)
        data = json.loads(resp.content)
        self.assertTrue(data['treatment']['requires_consent'])

    # ── T6: POST y PUT persisten requires_consent ──

    def test_create_with_requires_consent_true(self) -> None:
        """POST /api/treatments/ con requires_consent=true lo persiste."""
        payload = {
            'name': 'Botox', 'category': 'Facial', 'price': '100000',
            'requires_consent': True,
        }
        resp = self.client.post(
            '/api/treatments/', json.dumps(payload),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.content)
        self.assertTrue(data['treatment']['requires_consent'])
        self.assertTrue(Treatment.objects.get(id=data['treatment']['id']).requires_consent)

    def test_create_without_requires_consent_defaults_false(self) -> None:
        """POST /api/treatments/ sin requires_consent lo deja en False."""
        payload = {'name': 'Limpieza', 'category': 'Facial', 'price': '50000'}
        resp = self.client.post(
            '/api/treatments/', json.dumps(payload),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.content)
        self.assertFalse(data['treatment']['requires_consent'])

    def test_update_requires_consent(self) -> None:
        """PUT /api/treatments/:id/ actualiza requires_consent."""
        t = Treatment.objects.create(
            name='T1', slug='t1', category='Cat', price=100,
            requires_consent=False,
        )
        resp = self.client.put(
            f'/api/treatments/{t.id}/',
            json.dumps({'requires_consent': True}),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['treatment']['requires_consent'])
        t.refresh_from_db()
        self.assertTrue(t.requires_consent)
