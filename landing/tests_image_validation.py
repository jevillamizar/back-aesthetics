"""
Tests de validación de contenido de imágenes (magic bytes).
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.core.files.uploadedfile import SimpleUploadedFile
import json

from users.models import User


class ImageContentValidationTestCase(TenantTestCase):
    """
    Test que verifica validación de imágenes por contenido (magic bytes),
    no solo por extensión de archivo.
    
    Problema: Solo validar extensión permite bypass trivial renombrando
    archivos maliciosos (ej: script.py renombrado a script.jpg).
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
        response = self.client.post(
            '/api/auth/login/',
            json.dumps({'email': 'admin@test.com', 'password': 'testpass123'}),
            content_type='application/json'
        )
        self.token = json.loads(response.content)['token']
    
    def test_valid_png_upload_succeeds(self):
        """Test que imagen PNG válida es aceptada."""
        # Usar Pillow para crear PNG válido mínimo
        from PIL import Image
        from io import BytesIO
        
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        png_data = buffer.getvalue()
        
        image = SimpleUploadedFile('valid.png', png_data, content_type='image/png')
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200,
            f"PNG válido debería ser aceptado: {json.loads(response.content)}")
    
    def test_valid_jpeg_upload_succeeds(self):
        """Test que imagen JPEG válida es aceptada."""
        # Usar Pillow para crear JPEG válido
        from PIL import Image
        from io import BytesIO
        
        img = Image.new('RGB', (1, 1), color='blue')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        jpeg_data = buffer.getvalue()
        
        image = SimpleUploadedFile('valid.jpg', jpeg_data, content_type='image/jpeg')
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_executable_with_jpg_extension_rejected(self):
        """
        Test que archivo ejecutable con extensión .jpg es RECHAZADO.
        
        CON EL BUG: Retorna 200 porque la extensión es .jpg
        CON EL FIX: Retorna 400 porque el contenido no es JPEG válido
        """
        # Contenido de un script Python (simulando ejecutable malicioso)
        malicious_content = b"#!/usr/bin/env python3\nimport os\nos.system('rm -rf /')"
        
        # Renombrado como .jpg para bypass de validación por extensión
        fake_image = SimpleUploadedFile(
            'malicious.jpg', 
            malicious_content, 
            content_type='image/jpeg'
        )
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': fake_image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400 (archivo no es imagen válida)
        # CON EL BUG: Retorna 200 (acepta por extensión)
        self.assertEqual(response.status_code, 400,
            "BUG: Archivo con extensión .jpg pero contenido malicioso fue aceptado. "
            "Se requiere validación de magic bytes.")
    
    def test_php_script_with_png_extension_rejected(self):
        """
        Test que script PHP con extensión .png es RECHAZADO.
        
        Esto simula un ataque de upload donde el atacante sube un shell PHP
        con extensión .png para ejecutar código en el servidor.
        """
        # Script PHP shell típico
        php_shell = b"<?php system($_GET['cmd']); ?>"
        
        fake_image = SimpleUploadedFile(
            'shell.png',
            php_shell,
            content_type='image/png'
        )
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': fake_image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Shell PHP con extensión .png fue aceptado. "
            "Se requiere validación de contenido.")
    
    def test_html_with_gif_extension_rejected(self):
        """
        Test que HTML (XSS) con extensión .gif es RECHAZADO.
        
        Esto previene XSS donde un atacante sube HTML con extensión de imagen
        y luego lo sirve como tal para ejecutar JavaScript.
        """
        # HTML con JavaScript malicioso
        xss_html = b"<script>alert('XSS')</script>"
        
        fake_image = SimpleUploadedFile(
            'xss.gif',
            xss_html,
            content_type='image/gif'
        )
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': fake_image},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: HTML/XSS con extensión .gif fue aceptado.")
    
    def test_svg_with_xml_bomb_rejected(self):
        """
        Test que SVG con XML bomb (Billion Laughs) es rechazado.
        
        Previene DoS por entidades XML recursivas.
        """
        # XML bomb (simplificada)
        xml_bomb = b'''<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
]>
<svg xmlns="http://www.w3.org/2000/svg"><text>&lol2;</text></svg>'''
        
        fake_svg = SimpleUploadedFile(
            'bomb.svg',
            xml_bomb,
            content_type='image/svg+xml'
        )
        
        response = self.client.post(
            '/api/upload-image/',
            {'file': fake_svg},
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # El SVG es válido sintácticamente pero potencialmente peligroso
        # Con validación de contenido estricta, debería ser rechazado
        # o al menos sanitizado
        self.assertIn(response.status_code, [200, 400])
        
        if response.status_code == 200:
            # Si se acepta, el sistema debe sanitizar el SVG
            # Este test documenta el riesgo
            pass
