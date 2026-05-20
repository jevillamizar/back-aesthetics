"""
Tests de límite de trust indicators.
Problema 16: Backend no valida límite de 6 trust indicators.
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import json

from users.models import User
from landing.models import ClinicLanding


class TrustIndicatorsLimitTestCase(TenantTestCase):
    """
    Test que verifica que el backend valida máximo 6 trust indicators.
    
    CON EL BUG: Frontend limita a 6, pero backend acepta cualquier cantidad.
    CON EL FIX: Backend retorna 400 si hay más de 6.
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
    
    def test_valid_6_indicators_accepted(self):
        """6 indicators deben ser aceptados (límite máximo)."""
        indicators = [
            {'icon': 'star', 'label': f'Label {i}', 'sub': f'Sub {i}'}
            for i in range(6)
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': indicators}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
    
    def test_more_than_6_indicators_rejected(self):
        """Más de 6 indicators deben ser RECHAZADOS."""
        indicators = [
            {'icon': 'star', 'label': f'Label {i}', 'sub': f'Sub {i}'}
            for i in range(7)  # 7 es más que el límite
        ]
        
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': indicators}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        
        # CON EL FIX: Debe retornar 400
        self.assertEqual(response.status_code, 400,
            "BUG: Backend aceptó más de 6 trust indicators")
    
    def test_empty_indicators_allowed(self):
        """Array vacío debe ser permitido."""
        response = self.client.put(
            '/api/landing/',
            json.dumps({'trust_indicators': []}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        self.assertEqual(response.status_code, 200)
