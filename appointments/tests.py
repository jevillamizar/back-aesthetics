import json
from datetime import timedelta

from django.core import signing
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from appointments.models import Appointment
from medical_records.models import Consent, MedicalRecord
from patients.models import Patient
from treatments.models import Treatment
from users.models import User


class AppointmentDictRequiresConsentTest(TenantTestCase):
    """T8 — _appointment_to_dict incluye treatment_requires_consent."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        self.patient = Patient.objects.create(first_name='Ana', last_name='Test')
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        now = timezone.now() + timedelta(hours=1)

        self.treatment = Treatment.objects.create(
            name='Botox', slug='botox', category='Facial',
            price=100000, requires_consent=True,
        )
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            treatment=self.treatment,
            starts_at=now, ends_at=now + timedelta(hours=1),
            status='PENDING',
        )

    def test_includes_treatment_requires_consent_true(self) -> None:
        """GET /api/appointments/:id/ retorna treatment_requires_consent=true."""
        resp = self.client.get(f'/api/appointments/{self.appt.id}/', **self.auth)
        data = json.loads(resp.content)
        self.assertTrue(data['appointment']['treatment_requires_consent'])

    def test_includes_treatment_requires_consent_false(self) -> None:
        """treatment_requires_consent=false cuando treatment.requires_consent=False."""
        self.treatment.requires_consent = False
        self.treatment.save()
        resp = self.client.get(f'/api/appointments/{self.appt.id}/', **self.auth)
        data = json.loads(resp.content)
        self.assertFalse(data['appointment']['treatment_requires_consent'])

    def test_treatment_requires_consent_null_when_no_treatment(self) -> None:
        """treatment_requires_consent=null cuando la cita no tiene tratamiento."""
        self.appt.treatment = None
        self.appt.save()
        resp = self.client.get(f'/api/appointments/{self.appt.id}/', **self.auth)
        data = json.loads(resp.content)
        self.assertIsNone(data['appointment']['treatment_requires_consent'])


class AppointmentPatchMedicalRecordCreationTest(TenantTestCase):
    """T9 — PATCH a IN_PROGRESS condiciona la creación de MedicalRecord según enable_medical_history."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        self.patient = Patient.objects.create(first_name='Ana', last_name='Test')
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        now = timezone.now() + timedelta(hours=1)

        self.treatment = Treatment.objects.create(
            name='Botox', slug='botox', category='Facial', price=100000,
        )
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            treatment=self.treatment,
            starts_at=now, ends_at=now + timedelta(hours=1),
            status='PENDING',
        )

    def test_creates_medical_record_when_hc_enabled(self) -> None:
        """PATCH IN_PROGRESS crea MedicalRecord cuando enable_medical_history=True."""
        self.tenant.enable_medical_history = True
        self.tenant.save()
        resp = self.client.patch(
            f'/api/appointments/{self.appt.id}/',
            json.dumps({'status': 'IN_PROGRESS'}),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(MedicalRecord.objects.filter(appointment=self.appt).exists())

    def test_skips_medical_record_when_hc_disabled(self) -> None:
        """PATCH IN_PROGRESS NO crea MedicalRecord cuando enable_medical_history=False."""
        self.tenant.enable_medical_history = False
        self.tenant.save()
        resp = self.client.patch(
            f'/api/appointments/{self.appt.id}/',
            json.dumps({'status': 'IN_PROGRESS'}),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MedicalRecord.objects.filter(appointment=self.appt).exists())

    def test_completed_direct_does_not_create_medical_record(self) -> None:
        """PATCH COMPLETED directo no crea MedicalRecord."""
        self.tenant.enable_medical_history = False
        self.tenant.save()
        resp = self.client.patch(
            f'/api/appointments/{self.appt.id}/',
            json.dumps({'status': 'COMPLETED'}),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MedicalRecord.objects.filter(appointment=self.appt).exists())


class ConsentSignatureImageSizeLimitTest(TenantTestCase):
    """Verifica que signature_image rechaza payloads excesivamente grandes."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        self.patient = Patient.objects.create(first_name='Ana', last_name='Test')
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        now = timezone.now() + timedelta(hours=1)
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            starts_at=now, ends_at=now + timedelta(hours=1),
            status='PENDING',
        )

    def test_appointment_consent_accepts_normal_signature(self) -> None:
        """POST /api/appointments/:id/consent/ acepta firma de tamaño normal (~30KB)."""
        normal_sig = 'data:image/png;base64,' + ('A' * 30_000)
        resp = self.client.post(
            f'/api/appointments/{self.appt.id}/consent/',
            json.dumps({
                'signed_by_name': 'Ana Test',
                'signature_image': normal_sig,
            }),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 201)

    def test_appointment_consent_idempotent_when_already_signed(self) -> None:
        """POST duplicado retorna consent existente en vez de crear otro."""
        payload = json.dumps({
            'signed_by_name': 'Ana Test',
            'signature_image': 'data:image/png;base64,AAAA',
        })
        url = f'/api/appointments/{self.appt.id}/consent/'
        # Primero: crear MR para que el consent se vincule
        MedicalRecord.objects.create(
            patient=self.patient, doctor=self.admin, appointment=self.appt,
        )
        resp1 = self.client.post(url, payload, content_type='application/json', **self.auth)
        self.assertEqual(resp1.status_code, 201)
        id1 = json.loads(resp1.content)['consent']['id']

        resp2 = self.client.post(url, payload, content_type='application/json', **self.auth)
        self.assertEqual(resp2.status_code, 200)
        id2 = json.loads(resp2.content)['consent']['id']
        self.assertEqual(id1, id2)
        # Solo debe haber 1 consent para este MR
        self.assertEqual(Consent.objects.filter(medical_record__appointment=self.appt).count(), 1)

    def test_appointment_consent_rejects_oversized_signature(self) -> None:
        """POST /api/appointments/:id/consent/ rechaza firma > 200KB."""
        huge_sig = 'data:image/png;base64,' + ('A' * 300_000)
        resp = self.client.post(
            f'/api/appointments/{self.appt.id}/consent/',
            json.dumps({
                'signed_by_name': 'Ana Test',
                'signature_image': huge_sig,
            }),
            content_type='application/json', **self.auth,
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertIn('signature_image', data['detail'].lower())


class AppointmentCompleteEndpointTest(TenantTestCase):
    """Problema 5 — POST /api/appointments/:id/complete/ transacción atómica."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        self.patient = Patient.objects.create(first_name='Ana', last_name='Test')
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        now = timezone.now() + timedelta(hours=1)
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            starts_at=now, ends_at=now + timedelta(hours=1),
            status='IN_PROGRESS',
        )
        self.mr = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.admin, appointment=self.appt,
        )

    def _url(self) -> str:
        return f'/api/appointments/{self.appt.id}/complete/'

    def test_happy_path_all_three_succeed(self) -> None:
        """Las 3 operaciones exitosas → COMPLETED, MR actualizado, consent creado."""
        payload = {
            'medical_record': {'chief_complaint': 'Dolor cervical', 'diagnosis': 'Contractura'},
            'consent': {
                'signed_by_name': 'Ana Test',
                'signature_image': 'data:image/png;base64,AAAA',
                'procedure_description': 'Infiltración',
            },
        }
        resp = self.client.post(self._url(), json.dumps(payload), content_type='application/json', **self.auth)
        self.assertEqual(resp.status_code, 200)

        # Verificar estado cita
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'COMPLETED')

        # Verificar MR
        self.mr.refresh_from_db()
        self.assertEqual(self.mr.chief_complaint, 'Dolor cervical')
        self.assertEqual(self.mr.diagnosis, 'Contractura')

        # Verificar consent creado
        consent = Consent.objects.filter(medical_record=self.mr).first()
        self.assertIsNotNone(consent)
        self.assertEqual(consent.signed_by_name, 'Ana Test')
        self.assertIsNotNone(consent.signed_at)

    def test_rollback_when_no_medical_record(self) -> None:
        """Si la cita no tiene MR → error 400, nada cambia."""
        # Eliminar el MR
        self.mr.delete()
        payload = {
            'medical_record': {'chief_complaint': 'Test'},
        }
        resp = self.client.post(self._url(), json.dumps(payload), content_type='application/json', **self.auth)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('historia clínica', json.loads(resp.content)['detail'].lower())
        # Cita sigue IN_PROGRESS
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'IN_PROGRESS')

    def test_rollback_when_consent_invalid(self) -> None:
        """Si consent es inválido (sin signed_by_name) → rollback, MR NO guardado."""
        self.mr.chief_complaint = 'Original'
        self.mr.save()

        payload = {
            'medical_record': {'chief_complaint': 'Modificado'},
            'consent': {
                'signed_by_name': '',  # inválido
                'signature_image': 'data:image/png;base64,AAAA',
            },
        }
        resp = self.client.post(self._url(), json.dumps(payload), content_type='application/json', **self.auth)
        self.assertEqual(resp.status_code, 400)

        # MR NO modificado (rollback)
        self.mr.refresh_from_db()
        self.assertEqual(self.mr.chief_complaint, 'Original')

        # Cita sigue IN_PROGRESS
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'IN_PROGRESS')

        # No se creó consent
        self.assertEqual(Consent.objects.filter(medical_record=self.mr).count(), 0)

    def test_rollback_when_transition_invalid(self) -> None:
        """Si la cita ya está COMPLETED → error, ni MR ni consent persisten."""
        self.appt.status = 'COMPLETED'
        self.appt.save()
        self.mr.chief_complaint = 'Original'
        self.mr.save()

        payload = {
            'medical_record': {'chief_complaint': 'Nuevo'},
            'consent': {
                'signed_by_name': 'Ana Test',
                'signature_image': 'data:image/png;base64,AAAA',
            },
        }
        resp = self.client.post(self._url(), json.dumps(payload), content_type='application/json', **self.auth)
        self.assertEqual(resp.status_code, 400)

        # MR no cambia
        self.mr.refresh_from_db()
        self.assertEqual(self.mr.chief_complaint, 'Original')

        # Consent no creado
        self.assertEqual(Consent.objects.filter(medical_record=self.mr).count(), 0)

    def test_consent_omitted_module_disabled(self) -> None:
        """Body sin consent → solo guarda MR y marca COMPLETED sin error."""
        payload = {
            'medical_record': {'chief_complaint': 'Solo HC', 'diagnosis': 'OK'},
        }
        resp = self.client.post(self._url(), json.dumps(payload), content_type='application/json', **self.auth)
        self.assertEqual(resp.status_code, 200)

        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'COMPLETED')

        self.mr.refresh_from_db()
        self.assertEqual(self.mr.chief_complaint, 'Solo HC')

        # Sin consent
        self.assertEqual(Consent.objects.filter(medical_record=self.mr).count(), 0)


class ConsentFilterByMedicalRecordTest(TenantTestCase):
    """Problema 2 — GET /api/appointments/:id/consent/ filtra por medical_record, no por patient."""

    def setUp(self) -> None:
        self.client = TenantClient(self.tenant)
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Test1234!', role='ADMIN',
        )
        self.patient = Patient.objects.create(first_name='Ana', last_name='Test')
        token = signing.dumps({'uid': self.admin.pk}, salt='auth-token')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        now = timezone.now() + timedelta(hours=1)

        # Cita 1 con MR y Consent
        self.appt1 = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            starts_at=now, ends_at=now + timedelta(hours=1),
            status='IN_PROGRESS',
        )
        self.mr1 = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.admin, appointment=self.appt1,
        )
        self.consent1 = Consent.objects.create(
            patient=self.patient, doctor=self.admin, medical_record=self.mr1,
            signed_by_name='Firma Cita 1', signed_at=timezone.now(),
            signature_image='data:image/png;base64,AAA',
        )

        # Cita 2 con MR y Consent diferente
        self.appt2 = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=1),
            status='IN_PROGRESS',
        )
        self.mr2 = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.admin, appointment=self.appt2,
        )
        self.consent2 = Consent.objects.create(
            patient=self.patient, doctor=self.admin, medical_record=self.mr2,
            signed_by_name='Firma Cita 2', signed_at=timezone.now(),
            signature_image='data:image/png;base64,BBB',
        )

        # Cita 3 con MR pero SIN consent
        self.appt3 = Appointment.objects.create(
            patient=self.patient, doctor=self.admin,
            starts_at=now + timedelta(days=2), ends_at=now + timedelta(days=2, hours=1),
            status='IN_PROGRESS',
        )
        self.mr3 = MedicalRecord.objects.create(
            patient=self.patient, doctor=self.admin, appointment=self.appt3,
        )

    def test_returns_only_consent_for_this_appointment(self) -> None:
        """GET retorna SOLO el consent vinculado al MR de esta cita, no el de otra."""
        resp = self.client.get(f'/api/appointments/{self.appt1.id}/consent/', **self.auth)
        data = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data['consents']), 1)
        self.assertEqual(data['consents'][0]['id'], self.consent1.id)
        self.assertEqual(data['consents'][0]['signed_by_name'], 'Firma Cita 1')

    def test_single_consent_normal_case(self) -> None:
        """Cita con un solo consent → retorna ese consent correctamente."""
        resp = self.client.get(f'/api/appointments/{self.appt2.id}/consent/', **self.auth)
        data = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data['consents']), 1)
        self.assertEqual(data['consents'][0]['id'], self.consent2.id)
        self.assertEqual(data['consents'][0]['signed_by_name'], 'Firma Cita 2')

    def test_no_consent_returns_empty_list(self) -> None:
        """Cita sin consent → lista vacía, no devuelve consents de otras citas."""
        resp = self.client.get(f'/api/appointments/{self.appt3.id}/consent/', **self.auth)
        data = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data['consents']), 0)
