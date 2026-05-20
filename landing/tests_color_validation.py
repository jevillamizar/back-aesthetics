"""
Tests de validación de campos de color.
Problema 7: Campos de color permiten valores muy largos que permiten CSS injection.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class ColorValidationTestCase(TenantTestCase):
    """
    Test que verifica que campos de color solo aceptan valores válidos
    (hex, rgb, rgba, hsl, hsla, nombres CSS estándar) y no permiten
    inyección de código CSS malicioso.
    
    Problema: max_length=20 permite valores como:
    "#8B9E8B; body{background:red}" (CSS injection)
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
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
        
        self.landing = ClinicLanding.objects.create(
            headline="Test Landing",
            is_published=True
        )
    
    def test_valid_hex_color_accepted(self):
        """Colores HEX válidos deben ser aceptados."""
        valid_colors = {
            'primary_color': '#8B9E8B',
            'secondary_color': '#ff5733',
            'accent_color': '#000',
            'background_color': '#FFFFFF',
            'text_color': '#333',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(valid_colors),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['landing']['primary_color'], '#8B9E8B')
    
    def test_valid_rgb_color_accepted(self):
        """Colores RGB válidos deben ser aceptados."""
        payload = {
            'primary_color': 'rgb(139, 158, 139)',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_valid_css_name_accepted(self):
        """Nombres CSS válidos deben ser aceptados."""
        payload = {
            'primary_color': 'red',
            'secondary_color': 'blue',
            'accent_color': 'transparent',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_css_injection_with_semicolon_rejected(self):
        """
        Inyección CSS con punto y coma debe ser RECHAZADA.
        
        CON EL BUG: Acepta "#8B9E8B;}*{color:red"
        CON EL FIX: Retorna 400
        """
        # Inyección que cabe en 20 caracteres pero es maliciosa
        malicious_payload = {
            'primary_color': "#8B9E8B;}*{color:red",  # 20 chars exactos
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó inyección CSS con punto y coma")
        
        data = json.loads(response.content)
        self.assertIn('color', str(data).lower())
    
    def test_css_injection_with_braces_rejected(self):
        """
        Inyección CSS con llaves debe ser RECHAZADA.
        """
        # Inyección corta con llaves
        malicious_payload = {
            'secondary_color': "red}*{margin:0}",  # 14 chars
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(malicious_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó inyección CSS con llaves")
    
    def test_css_function_injection_rejected(self):
        """
        Funciones CSS maliciosas como url() deben ser rechazadas.
        """
        # Solo probar inyecciones que caben en 20 caracteres
        malicious_payloads = [
            {'primary_color': "url(//evil.com)"},  # 15 chars
            {'primary_color': "expression(XSS)"},  # 16 chars
        ]
        
        for payload in malicious_payloads:
            response = self.client.put(
                '/api/landing/',
                json.dumps(payload),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            
            self.assertEqual(response.status_code, 400,
                f"BUG: Se aceptó inyección CSS: {payload}")
    
    def test_invalid_color_format_rejected(self):
        """
        Formatos de color inválidos deben ser rechazados.
        """
        invalid_payloads = [
            {'primary_color': "not-a-color"},  # Texto arbitrario
            {'primary_color': "###"},  # Formato inválido
        ]
        
        for payload in invalid_payloads:
            response = self.client.put(
                '/api/landing/',
                json.dumps(payload),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            
            # CON EL FIX: Debe retornar 400
            # CON EL BUG: Retorna 200 aceptando cualquier string
            if response.status_code == 200:
                # Si pasa, es el bug - marcar como falla
                self.fail(f"BUG: Se aceptó color inválido: {payload}")
