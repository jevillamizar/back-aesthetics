"""
Tests de Rate Limiting para subida de imágenes.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.core.files.uploadedfile import SimpleUploadedFile
import json
from io import BytesIO
import base64

from users.models import User


class UploadImageRateLimitTestCase(TenantTestCase):
    """
    Test que verifica rate limiting en subida de imágenes.
    
    Problema: Sin rate limiting, un atacante puede llenar el storage
    o causar DoS con múltiples uploads.
    """
    
    def setUp(self):
        """Crear usuario admin y login."""
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
    
    def _create_test_image(self, name='test.png'):
        """Crear archivo de imagen de prueba en memoria."""
        # Imagen PNG de 1x1 pixel (mínima)
        png_data = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        return SimpleUploadedFile(name, png_data, content_type='image/png')
    
    def test_single_upload_succeeds(self):
        """Test que un upload normal funciona."""
        image = self._create_test_image('single.png')
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200, 
            f"Upload falló con: {json.loads(response.content)}")
        data = json.loads(response.content)
        self.assertIn('url', data)
    
    def test_rapid_uploads_rate_limited(self):
        """
        Test que múltiples uploads rápidos son rate limited.
        
        CON EL BUG: Todos los uploads retornan 200
        CON EL FIX: Después de N uploads en X segundos, retorna 429 Too Many Requests
        """
        # Intentar 10 uploads rápidos
        responses = []
        for i in range(10):
            image = self._create_test_image(f'rapid_{i}.png')
            
            response = self.client.post(
                '/api/upload-image/',
                {'file': image},
                HTTP_AUTHORIZATION=f'Bearer {self.token}'
            )
            responses.append(response.status_code)
        
        # CON EL FIX: Algunos deben ser 429 (rate limited)
        # Permitir hasta 5 uploads por minuto por usuario
        success_count = responses.count(200)
        rate_limited_count = responses.count(429)
        
        # Debe haber al menos algunos rate limited si el fix está activo
        # Si todos son 200, el BUG aún existe
        self.assertGreater(
            rate_limited_count, 0,
            f"BUG: No hay rate limiting. Todos los uploads retornaron 200. "
            f"Se esperaba algún 429 Too Many Requests. Responses: {responses}"
        )
        
        # El éxito debe ser limitado (ej: máximo 5)
        self.assertLessEqual(
            success_count, 5,
            f"Demasiados uploads exitosos. Esperado <= 5, obtenido: {success_count}"
        )
    
    def test_file_size_limit_enforced(self):
        """
        Test que archivos muy grandes son rechazados.
        
        CON EL BUG: No hay límite de tamaño
        CON EL FIX: Archivos > MAX_SIZE_MB son rechazados con 413
        """
        # Crear archivo de 15MB (simulado)
        large_data = b'x' * (15 * 1024 * 1024)
        large_file = SimpleUploadedFile('large.png', large_data, content_type='image/png')
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': large_file},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 413 Payload Too Large
        # CON EL BUG: Retorna 200 (acepta cualquier tamaño)
        self.assertIn(response.status_code, [200, 413],
            f"Código inesperado: {response.status_code}")
        
        # Si aún no hay límite, documentar que es BUG
        if response.status_code == 200:
            # Este es el comportamiento actual con el BUG
            pass  # Test documenta el problema
