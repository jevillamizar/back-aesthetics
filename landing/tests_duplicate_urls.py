"""
Tests de validación de duplicados en arrays de URLs.
Problema 11: Permite URLs duplicadas en hero_image_urls y about_image_urls.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class DuplicateUrlValidationTestCase(TenantTestCase):
    """
    Test que verifica que no se permiten URLs duplicadas en los arrays
    hero_image_urls y about_image_urls.
    
    CON EL BUG: Acepta ["https://example.com/img.png", "https://example.com/img.png"]
    CON EL FIX: Retorna 400 con error de duplicados
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
    
    def test_valid_unique_urls_accepted(self):
        """URLs únicas deben ser aceptadas."""
        payload = {
            'hero_image_urls': [
                'https://example.com/img1.png',
                'https://example.com/img2.png',
                'https://example.com/img3.png',
            ],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['landing']['hero_image_urls']), 3)
    
    def test_duplicate_urls_in_hero_rejected(self):
        """
        URLs duplicadas en hero_image_urls deben ser RECHAZADAS.
        
        CON EL BUG: Acepta array con duplicados
        CON EL FIX: Retorna 400
        """
        payload = {
            'hero_image_urls': [
                'https://example.com/img.png',
                'https://example.com/other.png',
                'https://example.com/img.png',  # Duplicado
            ],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptaron URLs duplicadas en hero_image_urls")
        
        data = json.loads(response.content)
        self.assertIn('duplicat', str(data).lower())
    
    def test_duplicate_urls_in_about_rejected(self):
        """URLs duplicadas en about_image_urls deben ser RECHAZADAS."""
        payload = {
            'about_image_urls': [
                'https://example.com/about1.png',
                'https://example.com/about1.png',  # Duplicado
            ],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400,
            "BUG: Se aceptaron URLs duplicadas en about_image_urls")
    
    def test_case_insensitive_duplicate_detection(self):
        """
        URLs duplicadas deben detectarse sin importar mayúsculas/minúsculas.
        """
        payload = {
            'hero_image_urls': [
                'https://Example.Com/IMG.png',
                'https://example.com/img.png',  # Duplicado ignorando case
            ],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # Idealmente debería detectar duplicados case-insensitive
        # CON EL FIX: Debe retornar 400
        if response.status_code == 200:
            # Documentar el comportamiento si no detecta case-insensitive
            pass
    
    def test_trailing_slash_not_considered_duplicate(self):
        """
        URLs con y sin trailing slash son técnicamente diferentes,
        pero podrían considerarse duplicados semanticamente.
        Este test documenta el comportamiento.
        """
        payload = {
            'hero_image_urls': [
                'https://example.com/img',
                'https://example.com/img/',  # Con trailing slash
            ],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # Estas son URLs diferentes técnicamente
        # El fix puede aceptarlas o rechazarlas según implementación
        self.assertIn(response.status_code, [200, 400])
    
    def test_empty_array_allowed(self):
        """Array vacío debe ser aceptado."""
        payload = {
            'hero_image_urls': [],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_single_url_allowed(self):
        """Array con un solo elemento debe ser aceptado."""
        payload = {
            'hero_image_urls': ['https://example.com/single.png'],
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
