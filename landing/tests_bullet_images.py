"""
Tests de limpieza de imágenes de bullets.
Problema 18: Eliminación de imágenes de bullets no limpia storage.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class BulletImagesCleanupTestCase(TenantTestCase):
    """
    Test que verifica limpieza de URLs de imágenes en about_bullets.
    Este test documenta el problema 18 — es principalmente un recordatorio
    de que las URLs de imágenes en JSON no se limpian del storage automáticamente.
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
        
        self.landing = ClinicLanding.objects.create(headline="Test")
    
    def test_bullet_image_urls_not_cleaned_automatically(self):
        """
        Documenta que las URLs de bullets no se limpian automáticamente.
        
        Este es un comportamiento conocido (no un bug crítico).
        Las URLs en about_bullets son strings, no archivos subidos por Django,
        por lo que no hay forma automática de saber si están en uso o no.
        
        RECOMENDACIÓN: Implementar tarea periódica de limpieza de storage
        o validación de URLs rotas.
        """
        # Agregar bullets con image_url
        bullets = [
            {'title': 'Experiencia', 'description': '10+ años', 'image_url': 'https://cdn.example.com/old1.png'},
            {'title': 'Calidad', 'image_url': 'https://cdn.example.com/old2.png'},
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'about_bullets': bullets}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
        
        # Actualizar bullets sin las URLs
        new_bullets = [
            {'title': 'Experiencia', 'description': '10+ años'},  # Sin image_url
            {'title': 'Calidad'},  # Sin image_url
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'about_bullets': new_bullets}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
        
        # Nota: Las URLs antiguas (old1.png, old2.png) NO se eliminan
        # del storage externo porque Django no tiene control sobre ellas.
        # Este test documenta este comportamiento esperado.
        
        # Si las URLs fueran archivos locales subidos via Django,
        # entonces sí deberían limpiarse. Pero al ser URLs externas,
        # solo es un string en la base de datos.
        
        data = json.loads(response.content)
        self.assertEqual(len(data['landing']['about_bullets']), 2)
        # Las nuevas bullets no tienen image_url
        for bullet in data['landing']['about_bullets']:
            self.assertNotIn('image_url', bullet)
    
    def test_external_urls_not_django_files(self):
        """
        Test que documenta que URLs externas no son archivos Django.
        """
        # Las URLs externas (http://, https://) son solo strings,
        # no archivos gestionados por Django Storage.
        # Por tanto, no hay limpieza automática posible.
        
        bullets = [
            {'title': 'Test', 'image_url': 'https://external.com/image.png'},
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'about_bullets': bullets}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
        
        # La URL está guardada pero no es un archivo de Django
        self.landing.refresh_from_db()
        self.assertEqual(
            self.landing.about_bullets[0]['image_url'],
            'https://external.com/image.png'
        )
