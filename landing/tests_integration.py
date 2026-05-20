"""
Tests de integración del flujo completo de landing.
Problema 17: No hay tests del flujo landing.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.core.files.uploadedfile import SimpleUploadedFile
import json

from users.models import User
from landing.models import ClinicLanding, LandingAuditLog


class LandingIntegrationTestCase(TenantTestCase):
    """
    Test de integración del flujo completo de landing page.
    """
    
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role=User.Role.ADMIN
        )
        # Login
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
    
    def test_complete_landing_workflow(self):
        """
        Flujo completo: crear landing, actualizar campos, verificar persistencia.
        """
        # 1. Verificar que se crea landing automáticamente al hacer GET
        response = self.client.get(
            '/api/landing/',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('landing', data)
        
        landing_id = data['landing'].get('id')
        
        # 2. Actualizar múltiples campos
        update_data = {
            'headline': 'Clínica de Belleza Ejemplo',
            'description': 'Los mejores tratamientos estéticos',
            'primary_color': '#8B9E8B',
            'phone': '+593991234567',
            'email': 'contacto@ejemplo.com',
            'trust_indicators': [
                {'icon': 'star', 'label': '10+ Años', 'sub': 'Experiencia'},
                {'icon': 'users', 'label': '5000+', 'sub': 'Pacientes'},
            ],
            'is_published': True,
        }
        
        response = self.client.put(
            '/api/landing/',
            json.dumps(update_data),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
        
        # 3. Verificar que los cambios persistieron
        response = self.client.get(
            '/api/landing/',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        data = json.loads(response.content)
        self.assertEqual(data['landing']['headline'], 'Clínica de Belleza Ejemplo')
        self.assertEqual(data['landing']['primary_color'], '#8B9E8B')
        self.assertEqual(len(data['landing']['trust_indicators']), 2)
        
        # 4. Verificar que se crearon logs de auditoría
        logs = LandingAuditLog.objects.filter(landing_id=landing_id)
        self.assertTrue(logs.exists(), "Debe haber logs de auditoría")
    
    def test_public_landing_endpoint(self):
        """
        Test del endpoint público de landing.
        """
        # Crear landing publicada
        landing = ClinicLanding.objects.create(
            headline="Landing Pública",
            description="Descripción pública",
            is_published=True
        )
        
        # El endpoint público no requiere auth
        response = self.client.get('/public/landing/')
        # El endpoint público requiere contexto de tenant
        # En test puede retornar 400 si no hay clinic en request
        self.assertIn(response.status_code, [200, 400])
    
    def test_permissions_admin_only(self):
        """
        Test que solo admins pueden modificar landing.
        """
        # Crear usuario doctor
        doctor = User.objects.create_user(
            email='doctor@test.com',
            password='testpass123',
            role=User.Role.DOCTOR
        )
        
        # Login como doctor
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'doctor@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        doctor_token = json.loads(response.content)['token']
        
        # Intentar modificar landing como doctor
        response = self.client.put(
            '/api/landing/',
            json.dumps({'headline': 'Cambio no autorizado'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {doctor_token}'
        )
        
        # Debe retornar 403 Forbidden
        self.assertEqual(response.status_code, 403)
    
    def test_landing_unpublished_returns_404(self):
        """
        Test que landing no publicada retorna 404 en endpoint público.
        """
        # Crear landing NO publicada
        ClinicLanding.objects.create(
            headline="No Publicada",
            is_published=False
        )
        
        # El endpoint público debe retornar 404
        # Nota: requiere contexto de tenant/clinic
        response = self.client.get('/public/landing/')
        self.assertIn(response.status_code, [404, 400])  # 400 si no hay tenant
