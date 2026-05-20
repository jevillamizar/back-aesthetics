"""
Tests de sanitización de URLs en campos de redes sociales.
Problema 6: URLs peligrosas (javascript:, data:) no son rechazadas.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class SocialUrlSanitizationTestCase(TenantTestCase):
    """
    Test que verifica que URLs maliciosas en campos de redes sociales
    son rechazadas para prevenir XSS.
    
    Problema: URLField valida formato pero no sanitiza protocolos peligrosos
    como javascript:, data:, vbscript:, file:, etc.
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
            headline="Test Landing",
            is_published=True
        )
    
    def test_valid_http_url_accepted(self):
        """URLs HTTP/HTTPS válidas deben ser aceptadas."""
        valid_urls = {
            'booking_url': 'https://calendly.com/clinica/turno',
            'instagram_url': 'https://instagram.com/clinica',
            'facebook_url': 'https://facebook.com/clinica',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(valid_urls),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['landing']['booking_url'], valid_urls['booking_url'])
    
    def test_javascript_url_rejected(self):
        """
        URLs con protocolo javascript: deben ser RECHAZADAS.
        
        CON EL BUG: Retorna 200, acepta URL maliciosa
        CON EL FIX: Retorna 400 con mensaje de error
        """
        malicious_payload = {
            'booking_url': "javascript:alert('XSS')",
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó URL con protocolo javascript: — riesgo de XSS")
        
        data = json.loads(response.content)
        self.assertIn('URL', data.get('detail', '') or 
                      str(data.get('errors', {})))
    
    def test_data_url_rejected(self):
        """
        URLs con protocolo data: deben ser RECHAZADAS.
        Podrían usarse para inyectar contenido malicioso.
        """
        malicious_payload = {
            'instagram_url': "data:text/html,<script>alert('XSS')</script>",
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó URL con protocolo data: — riesgo de XSS")
    
    def test_vbscript_url_rejected(self):
        """URLs con protocolo vbscript: deben ser RECHAZADAS."""
        malicious_payload = {
            'facebook_url': "vbscript:msgbox('XSS')",
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó URL con protocolo vbscript: — riesgo de XSS")
    
    def test_file_url_rejected(self):
        """URLs con protocolo file: deben ser RECHAZADAS (acceso local)."""
        malicious_payload = {
            'booking_url': "file:///etc/passwd",
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó URL con protocolo file: — riesgo de acceso local")
    
    def test_about_blank_rejected(self):
        """about:blank puede usarse para bypass, debe ser rechazado."""
        malicious_payload = {
            'booking_url': "about:blank",
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó URL about:blank")
