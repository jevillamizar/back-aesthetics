"""
Tenant-based permission system for admin access control
"""
from django.contrib.auth.backends import ModelBackend
from django.db import connection
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


class TenantPermissionMiddleware:
    """
    Middleware to enforce tenant-based access control for admin
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Only check admin paths (but allow login page)
        if request.path.startswith('/admin/') and not request.path.startswith('/admin/login'):
            user = request.user
            
            # If user is authenticated, check permissions
            if user.is_authenticated:
                current_schema = connection.schema_name
                
                # Public schema admin - only allow superusers
                if current_schema == 'public':
                    if not user.is_superuser:
                        return HttpResponseForbidden(
                            '<h1>403 Forbidden</h1>'
                            '<p>Only superusers can access the public admin panel.</p>'
                            '<p>Please access your clinic admin at: http://[your-clinic].lvh.me:8000/admin/</p>'
                        )
                
                # Tenant schema admin - only allow staff users
                else:
                    if not user.is_staff:
                        return HttpResponseForbidden(
                            '<h1>403 Forbidden</h1>'
                            '<p>You do not have permission to access this admin panel.</p>'
                        )
        
        response = self.get_response(request)
        return response


class TenantAuthBackend(ModelBackend):
    """
    Backend de autenticación para la capa de API (Option A: users en TENANT_APPS).

    - Bug 1 fix: acepta email= como kwarg además de username= (auth_login usa email=).
    - Bug 2 fix: valida role (ADMIN/DOCTOR) en lugar de is_staff.
    - Option A: el ORM aísla usuarios por schema automáticamente. No se necesita
      validar clinic FK ni is_superuser — User.objects.get() ya busca solo en el
      schema activo. En public schema, users_user no existe → ProgrammingError → None.

    NOTA: TenantPermissionMiddleware sigue usando is_staff para /admin/ — correcto,
    no se modifica aquí.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        from django.db.utils import ProgrammingError

        from users.models import User

        # Bug 1 fix: auth_login llama authenticate(request, email=..., password=...).
        # Acepta email= como alias de username= para compatibilidad.
        email = username or kwargs.get('email')

        if email is None or password is None:
            return None

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Llamada dummy al hasher para mitigar timing attacks
            User().set_password(password)
            return None
        except ProgrammingError:
            # En public schema, users_user no existe (users está en TENANT_APPS).
            # Retorna None de forma segura en lugar de propagar la excepción.
            return None

        if not user.check_password(password):
            return None

        # Verifica is_active via método estándar heredado de ModelBackend
        if not self.user_can_authenticate(user):
            return None

        # Bug 2 fix: validar role de API — solo ADMIN y DOCTOR pueden acceder a /api/*.
        # El aislamiento por tenant ya lo garantiza el ORM (search_path por schema).
        if user.role not in (User.Role.ADMIN, User.Role.DOCTOR):
            return None

        return user
