"""
Tests de validación de campos de contacto.
Problema 13: phone, whatsapp_phone sin validación de formato.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class ContactValidationTestCase(TenantTestCase):
    """
    Test que verifica validación de campos de contacto.
    """
    
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role=User.Role.ADMIN
        )
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
        
        self.landing = ClinicLanding.objects.create(headline="Test")
    
    def test_valid_phone_accepted(self):
        """Teléfonos válidos deben ser aceptados."""
        valid_phones = [
            '+593991234567',
            '0991234567',
            '02-123-4567',
            '(02) 123-4567',
        ]
        
        for phone in valid_phones:
            response = self.client.put(
                '/api/landing/',
                json.dumps({'phone': phone}),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            self.assertEqual(response.status_code, 200, f"Teléfono {phone} debería ser válido")
    
    def test_valid_whatsapp_accepted(self):
        """WhatsApp válido debe ser aceptado."""
        response = self.client.put(
            '/api/landing/',
            json.dumps({'whatsapp_phone': '+593991234567'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
    
    def test_invalid_phone_rejected(self):
        """Teléfonos con caracteres inválidos deben ser rechazados."""
        invalid_phones = [
            'abc123',
            'phone@domain.com',
            '<script>alert(1)</script>',
        ]
        
        for phone in invalid_phones:
            response = self.client.put(
                '/api/landing/',
                json.dumps({'phone': phone}),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            # CON EL FIX: Debe retornar 400
            # CON EL BUG: Retorna 200
            if response.status_code == 200:
                self.fail(f"BUG: Teléfono inválido aceptado: {phone}")
    
    def test_empty_phone_allowed(self):
        """Campo vacío debe ser permitido."""
        response = self.client.put(
            '/api/landing/',
            json.dumps({'phone': '', 'whatsapp_phone': ''}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
