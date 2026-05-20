"""
Tests para el módulo landing.

Nota: landing es TENANT_APP, por lo que los tests que hacen queries
a la BD deben usar TenantTestCase.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection, transaction
from django.db.utils import IntegrityError
from threading import Thread
import time
import json

from landing.models import ClinicLanding
from users.models import User


class ClinicLandingSingletonTestCase(TenantTestCase):
    """Test que verifica que solo puede existir un ClinicLanding por tenant."""

    def test_multiple_landing_creation_should_fail(self):
        """
        Test que demuestra la race condition:
        Sin constraint de unicidad, se pueden crear múltiples ClinicLanding.
        
        Este test DEBE FALLAR inicialmente (demostrando el bug),
        y PASAR después de agregar el constraint de unicidad.
        """
        # Creamos el primer landing (debería funcionar)
        landing1 = ClinicLanding.objects.create(
            headline="Landing 1",
            is_published=True
        )
        self.assertIsNotNone(landing1.id)
        
        # Intentamos crear un segundo landing
        # CON EL BUG: Esto funcionará y creará un duplicado
        # CON EL FIX: Esto debe fallar con IntegrityError
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClinicLanding.objects.create(
                    headline="Landing 2",
                    is_published=False
                )
        
        # Verificar que solo existe 1 landing
        count = ClinicLanding.objects.count()
        self.assertEqual(count, 1, 
            f"Se encontraron {count} landings, debe existir solo 1 por tenant")
    
    def test_get_or_create_should_return_existing(self):
        """
        Test que verifica que get_or_create retorna el existente
        y no crea duplicados.
        """
        # Crear inicial
        landing1, created1 = ClinicLanding.objects.get_or_create(
            defaults={'headline': 'Original'}
        )
        self.assertTrue(created1)
        
        # Simular race condition con get_or_create
        landing2, created2 = ClinicLanding.objects.get_or_create(
            defaults={'headline': 'Duplicate'}
        )
        
        # Debe retornar el mismo objeto
        self.assertEqual(landing1.id, landing2.id)
        self.assertFalse(created2)
        
        # Solo debe existir 1
        self.assertEqual(ClinicLanding.objects.count(), 1)


class ClinicLandingSchemaIsolationTestCase(TenantTestCase):
    """Test que verifica que diferentes tenants pueden tener sus propios landings."""
    
    def test_different_tenants_can_have_landing(self):
        """
        Cada tenant debe poder tener su propio ClinicLanding sin interferir
        con otros tenants.
        """
        # Este test corre en el schema del tenant de prueba
        landing = ClinicLanding.objects.create(headline="Tenant Landing")
        
        # Verificar que existe en este schema
        self.assertEqual(ClinicLanding.objects.count(), 1)
        self.assertEqual(landing.headline, "Tenant Landing")


class LandingJsonValidationTestCase(TenantTestCase):
    """
    Test que verifica la validación de schema JSON en campos de landing.
    
    Problema: Sin validación de schema, se acepta cualquier estructura JSON válida,
    lo que puede romper el frontend público que espera campos específicos.
    """

    def setUp(self):
        """Crear usuario admin para autenticación en tests."""
        self.client = TenantClient(self.tenant)
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role=User.Role.ADMIN,
            first_name='Admin',
            last_name='Test'
        )
        # Login para obtener token
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
    
    def test_valid_trust_indicators_accepted(self):
        """Test que estructura válida de trust_indicators es aceptada."""
        valid_indicators = [
            {"icon": "clock", "label": "15+ Años", "sub": "Experiencia"},
            {"icon": "star", "label": "4.9/5", "sub": "Rating"}
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': valid_indicators}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['landing']['trust_indicators'], valid_indicators)
    
    def test_invalid_trust_indicators_rejected(self):
        """
        Test que estructura inválida de trust_indicators es RECHAZADA.
        
        CON EL BUG: Retorna 200 y guarda datos malformados
        CON EL FIX: Retorna 400 con mensaje de error de validación
        """
        invalid_indicators = [
            {"malicious": "data", "invalid_field": True},  # Falta icon, label, sub
            "not an object",  # String en lugar de objeto
            123  # Número en lugar de objeto
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': invalid_indicators}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('detail', data)
        self.assertIn('trust_indicators', data['detail'].lower())
    
    def test_valid_testimonials_accepted(self):
        """Test que estructura válida de testimonials es aceptada."""
        valid_testimonials = [
            {
                "name": "Sarah M.",
                "treatment": "Botox",
                "rating": 5,
                "quote": "Excelente servicio"
            }
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'testimonials': valid_testimonials}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_invalid_testimonials_rejected(self):
        """
        Test que testimonial sin campos requeridos es RECHAZADO.
        
        CON EL BUG: Retorna 200
        CON EL FIX: Retorna 400
        """
        invalid_testimonials = [
            {"name": "John"}  # Falta treatment, rating, quote
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'testimonials': invalid_testimonials}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_valid_image_urls_accepted(self):
        """Test que array de URLs válido es aceptado."""
        valid_urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.png"
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'hero_image_urls': valid_urls}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_invalid_image_urls_rejected(self):
        """
        Test que URLs inválidas son RECHAZADAS.
        
        CON EL BUG: Acepta cualquier string
        CON EL FIX: Rechaza URLs malformadas o con protocolos peligrosos
        """
        invalid_urls = [
            "javascript:alert('xss')",  # Protocolo peligroso
            "not-a-url",  # URL inválida
            123  # No es string
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'hero_image_urls': invalid_urls}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_non_array_json_rejected_for_array_fields(self):
        """
        Test que enviar un objeto en lugar de array es rechazado.
        
        CON EL BUG: Acepta cualquier JSON válido
        CON EL FIX: Rechaza cuando no es array
        """
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': {"not": "an array"}}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 400)
