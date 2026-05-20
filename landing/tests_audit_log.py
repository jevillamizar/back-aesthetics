"""
Tests de Audit Log para cambios en landing page.
Problema 8: No hay control de versiones ni historial de cambios.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding, LandingAuditLog


class AuditLogTestCase(TenantTestCase):
    """
    Test que verifica que se registra un audit log cuando se modifican
    campos del landing page.
    
    CON EL BUG: Al guardar cambios, no se crea registro de auditoría.
    CON EL FIX: Se crea LandingAuditLog con quién, cuándo y qué cambió.
    """
    
    def setUp(self):
        """Crear usuario admin y landing."""
        self.client = TenantClient(self.tenant)
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role=User.Role.ADMIN,
            first_name='Admin',
            last_name='Test'
        )
        # Login
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
        
        # Crear landing inicial
        self.landing = ClinicLanding.objects.create(
            headline="Título Original",
            description="Descripción original",
            primary_color="#FF0000",
            is_published=True
        )
    
    def test_audit_log_created_on_update(self):
        """
        Test que al actualizar landing se crea registro de auditoría.
        
        CON EL FIX: Debe existir LandingAuditLog después del PUT.
        """
        # Verificar que no hay logs previos
        initial_count = LandingAuditLog.objects.filter(
            landing=self.landing
        ).count()
        
        # Modificar landing
        response = self.client.put(
            '/api/landing/',
            json.dumps({
                'headline': 'Título Modificado',
                'description': 'Descripción modificada',
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # CON EL FIX: Debe haberse creado logs de auditoría
        final_count = LandingAuditLog.objects.filter(
            landing=self.landing
        ).count()
        
        self.assertGreater(
            final_count, initial_count,
            "BUG: No se creó registro de auditoría después de modificar landing"
        )
    
    def test_audit_log_records_user(self):
        """
        Test que el audit log registra correctamente el usuario que hizo el cambio.
        """
        # Modificar landing
        self.client.put(
            '/api/landing/',
            json.dumps({'headline': 'Otro título'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # Verificar que se registró el usuario
        log = LandingAuditLog.objects.filter(
            landing=self.landing
        ).first()
        
        # CON EL FIX: Debe existir log con el usuario correcto
        self.assertIsNotNone(log, "BUG: No se creó log de auditoría")
        self.assertEqual(
            log.changed_by_id, self.admin_user.id,
            "BUG: El log no registra el usuario que hizo el cambio"
        )
    
    def test_audit_log_records_field_changes(self):
        """
        Test que el audit log registra qué campo cambió y los valores old/new.
        """
        old_headline = self.landing.headline
        new_headline = 'Nuevo Título Auditado'
        
        # Modificar un campo específico
        self.client.put(
            '/api/landing/',
            json.dumps({'headline': new_headline}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # Buscar log específico para el campo headline
        log = LandingAuditLog.objects.filter(
            landing=self.landing,
            field_name='headline'
        ).first()
        
        # CON EL FIX: Debe existir log con old_value y new_value
        self.assertIsNotNone(log, "BUG: No se creó log para el campo headline")
        self.assertEqual(log.old_value, old_headline)
        self.assertEqual(log.new_value, new_headline)
    
    def test_audit_log_not_created_when_no_changes(self):
        """
        Test que no se crea log si el valor no cambió realmente.
        """
        # Enviar mismo valor que ya tiene
        current_headline = self.landing.headline
        
        initial_count = LandingAuditLog.objects.filter(
            landing=self.landing
        ).count()
        
        self.client.put(
            '/api/landing/',
            json.dumps({'headline': current_headline}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        final_count = LandingAuditLog.objects.filter(
            landing=self.landing
        ).count()
        
        # No debe haberse creado log si no hubo cambio real
        self.assertEqual(final_count, initial_count,
            "Se creó log innecesario cuando no hubo cambio real")
    
    def test_audit_log_timestamp_auto_set(self):
        """
        Test que el timestamp se establece automáticamente.
        """
        from django.utils import timezone
        
        before_update = timezone.now()
        
        self.client.put(
            '/api/landing/',
            json.dumps({'headline': 'Con timestamp'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        after_update = timezone.now()
        
        log = LandingAuditLog.objects.filter(
            landing=self.landing
        ).first()
        
        self.assertIsNotNone(log)
        self.assertTrue(
            before_update <= log.changed_at <= after_update,
            "BUG: El timestamp no se estableció correctamente"
        )
