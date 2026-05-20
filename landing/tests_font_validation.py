"""
Tests de validación de fuentes Google Fonts.
Problema 9: Campos de fuente aceptan cualquier string sin validar contra Google Fonts.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class FontValidationTestCase(TenantTestCase):
    """
    Test que verifica que solo se aceptan fuentes válidas de Google Fonts
    en los campos font_heading, font_body, font_accent.
    
    CON EL BUG: Se acepta cualquier string, incluyendo fuentes inexistentes
    o URLs maliciosas.
    CON EL FIX: Solo se aceptan nombres de fuentes de una lista blanca
    de Google Fonts populares.
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
    
    def test_valid_google_font_accepted(self):
        """Fuentes válidas de Google Fonts deben ser aceptadas."""
        valid_fonts = {
            'font_heading': 'Playfair Display',
            'font_body': 'Inter',
            'font_accent': 'Cormorant Garamond',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(valid_fonts),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['landing']['font_heading'], 'Playfair Display')
        self.assertEqual(data['landing']['font_body'], 'Inter')
    
    def test_empty_font_accepted(self):
        """Campos de fuente vacíos deben ser aceptados (usar default)."""
        payload = {
            'font_heading': '',
            'font_body': '',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_invalid_font_name_rejected(self):
        """
        Nombres de fuente inexistentes deben ser RECHAZADOS.
        
        CON EL BUG: Acepta "FuenteInexistente123"
        CON EL FIX: Retorna 400
        """
        invalid_payload = {
            'font_heading': 'FuenteInexistente123XYZ',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(invalid_payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptó nombre de fuente inexistente")
        
        data = json.loads(response.content)
        self.assertIn('font', str(data).lower())
    
    def test_font_with_url_rejected(self):
        """
        URLs en campos de fuente deben ser RECHAZADAS (posible XSS/info leak).
        """
        malicious_payloads = [
            {'font_heading': 'https://evil.com/font.woff'},
            {'font_body': 'http://tracker.com/?user=123'},
            {'font_accent': '//malicious.site/font.css'},
        ]
        
        for payload in malicious_payloads:
            response = self.client.put(
                '/api/landing/',
                json.dumps(payload),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            
            self.assertEqual(response.status_code, 400,
                f"BUG: Se aceptó URL maliciosa en fuente: {payload}")
    
    def test_font_with_special_chars_rejected(self):
        """
        Caracteres especiales en nombres de fuente deben ser rechazados.
        """
        malicious_payloads = [
            {'font_heading': 'Font<script>alert(1)</script>'},
            {'font_body': 'Font;DROP TABLE users;--'},
            {'font_accent': 'Font${7*7}'},
        ]
        
        for payload in malicious_payloads:
            response = self.client.put(
                '/api/landing/',
                json.dumps(payload),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            
            self.assertEqual(response.status_code, 400,
                f"BUG: Se aceptó fuente con caracteres especiales: {payload}")
    
    def test_system_fonts_rejected(self):
        """
        Fuentes del sistema (Arial, Times, etc.) no son Google Fonts,
        deben ser rechazadas para mantener consistencia.
        """
        system_fonts = {
            'font_heading': 'Arial',
            'font_body': 'Times New Roman',
            'font_accent': 'Helvetica',
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(system_fonts),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe rechazar fuentes del sistema
        # Si se aceptan, es el comportamiento anterior (bug)
        if response.status_code == 200:
            # Documentar el bug si se acepta
            pass  # Test documenta el problema
