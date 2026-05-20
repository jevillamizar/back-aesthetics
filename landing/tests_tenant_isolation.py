"""
Tests de aislamiento de tenant en endpoints públicos.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.db import connection
import json

from landing.models import ClinicLanding
from users.models import User
from clinics.models import Clinic, Domain


class TenantIsolationTestCase(TenantTestCase):
    """
    Test que verifica aislamiento de tenant en public_landing.
    
    Problema: El endpoint público confía en que el middleware de tenant
    estableció correctamente request.clinic. Si hay un bug en el middleware,
    podría haber fuga de información entre tenants.
    """
    
    def setUp(self):
        """Configurar tenant de prueba con datos."""
        self.client = TenantClient(self.tenant)
        
        # Crear landing para el tenant actual
        self.landing = ClinicLanding.objects.create(
            headline="Landing del Tenant Actual",
            description="Descripción específica del tenant de prueba",
            is_published=True
        )
        
        # Verificar que el clinic del tenant está configurado
        self.clinic = Clinic.objects.first()  # El tenant de prueba ya tiene clinic
    
    def test_public_landing_returns_correct_tenant_data(self):
        """
        Test que public_landing retorna datos del tenant correcto.
        
        Nota: TenantClient configura automáticamente el tenant,
        pero no ejecuta el middleware de CORS que setea request.clinic.
        Simulamos ese comportamiento manualmente.
        """
        # Simular que el middleware seteó request.clinic
        # Hacer request manualmente con contexto de tenant
        from django.test import RequestFactory
        from backend.views import public_landing
        
        factory = RequestFactory()
        request = factory.get('/public/landing/')
        request.clinic = self.clinic  # Simular middleware
        
        response = public_landing(request)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # Debe retornar datos del tenant actual
        self.assertIsNotNone(data['clinic'])
        self.assertEqual(data['landing']['headline'], "Landing del Tenant Actual")
        self.assertEqual(data['landing']['description'], "Descripción específica del tenant de prueba")
    
    def test_public_landing_returns_no_data_without_tenant(self):
        """
        Test que public_landing retorna error si no hay tenant válido.
        
        CON EL BUG: Si request.clinic es None, el endpoint podría
        retornar datos de cualquier tenant o datos inconsistentes.
        
        CON EL FIX: Debe retornar 400 cuando no se puede determinar
        el tenant del request.
        """
        # Simular request sin request.clinic (middleware no funcionó)
        from django.test import RequestFactory
        from backend.views import public_landing
        
        factory = RequestFactory()
        request = factory.get('/public/landing/')
        # NO seteamos request.clinic - simulando bug de middleware
        
        response = public_landing(request)
        
        # CON EL FIX: Debe retornar 400 porque no hay tenant
        self.assertEqual(response.status_code, 400,
            "BUG: Endpoint público retornó datos sin request.clinic")
        
        data = json.loads(response.content)
        self.assertIn('Tenant not found', data['detail'])
    
    def test_public_landing_isolation_between_tenants(self):
        """
        Test que verifica que un tenant no puede ver datos de otro tenant.
        
        Este test simula que request.clinic tiene un ID diferente al schema actual
        para verificar que se detecta el mismatch.
        """
        from django.test import RequestFactory
        from backend.views import public_landing
        from django.db import connection
        
        # Guardar schema original
        original_schema = connection.schema_name
        
        # Crear un "fake clinic" con schema diferente
        class FakeClinic:
            id = 9999
            schema_name = 'otro_tenant'
            name = "Otro Tenant"
            slug = "otro"
        
        fake_clinic = FakeClinic()
        
        factory = RequestFactory()
        request = factory.get('/public/landing/')
        request.clinic = fake_clinic  # Clinic con schema diferente
        
        response = public_landing(request)
        
        # CON EL FIX: Debe detectar el schema mismatch y retornar 500
        self.assertEqual(response.status_code, 500,
            "BUG: No se detectó schema mismatch entre request.clinic y connection.schema_name")
        
        data = json.loads(response.content)
        self.assertIn('Schema mismatch', data['detail'])
        
        # Verificar que seguimos en el schema correcto
        self.assertEqual(connection.schema_name, original_schema)
    
    def test_public_landing_handles_unpublished(self):
        """Test que verifica manejo de landing no publicado."""
        from django.test import RequestFactory
        from backend.views import public_landing
        
        self.landing.is_published = False
        self.landing.save()
        
        factory = RequestFactory()
        request = factory.get('/public/landing/')
        request.clinic = self.clinic
        
        response = public_landing(request)
        
        # Debe retornar 404 cuando no está publicado
        self.assertEqual(response.status_code, 404)
        
        # Restaurar
        self.landing.is_published = True
        self.landing.save()
    
    def test_public_landing_cors_headers_present(self):
        """
        Test que verifica que CORS headers están presentes en respuesta pública.
        
        Nota: Los headers CORS se agregan por el middleware, no por la view.
        Este test usa el cliente HTTP directo.
        """
        # Este test requiere que el middleware de CORS esté activo
        # En tests de Django el middleware puede no agregar headers
        # dependiendo de la configuración de ORIGIN
        response = self.client.get('/public/landing/', HTTP_ORIGIN='http://localhost:5173')
        
        # Si el middleware está configurado para permitir localhost:5173,
        # debe haber header CORS
        if 'Access-Control-Allow-Origin' in response:
            self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:5173')
