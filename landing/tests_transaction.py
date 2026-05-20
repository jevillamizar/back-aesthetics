"""
Tests de transacción atómica en guardado de landing.
Problema 12: Si el save() falla después de procesar archivos, queda estado inconsistente.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
import json

from users.models import User
from landing.models import ClinicLanding


class TransactionRollbackTestCase(TenantTestCase):
    """
    Test que verifica que las operaciones de landing son atómicas.
    Si hay un error, no debe quedar estado parcial committeado.
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
        
        self.landing = ClinicLanding.objects.create(
            headline="Título Original",
            description="Descripción Original",
            is_published=True
        )
    
    def test_atomic_save_on_error(self):
        """
        Test que si hay error en validación, no se guardan cambios parciales.
        
        Enviamos payload mixto con campos válidos e inválidos.
        CON FIX: Todo debe fallar, no quedar cambios parciales.
        """
        # Guardar estado original
        original_headline = self.landing.headline
        original_description = self.landing.description
        
        # Intentar actualización que parcialmente es inválida
        # El campo headline cambia, pero el color es inválido (debería fallar todo)
        response = self.client.put(
            '/api/landing/',
            json.dumps({
                'headline': 'Nuevo Título',
                'primary_color': '#8B9E8B;}*{color:red',  # Inválido
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # Debe fallar por color inválido
        self.assertEqual(response.status_code, 400)
        
        # Verificar que headline NO cambió (atomicidad)
        self.landing.refresh_from_db()
        self.assertEqual(
            self.landing.headline, original_headline,
            "BUG: Cambios parciales persistieron a pesar del error"
        )
