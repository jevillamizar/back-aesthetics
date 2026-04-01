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
    Custom authentication backend that validates users in the correct schema
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user in the current schema context
        """
        from users.models import User
        from django.db import connection
        
        if username is None or password is None:
            return None
        
        try:
            # Try to get user from current schema
            user = User.objects.get(email=username)
            
            # Check password
            if user.check_password(password):
                # For public schema, only allow superusers
                if connection.schema_name == 'public' and not user.is_superuser:
                    return None
                
                # For tenant schemas, allow staff users
                if connection.schema_name != 'public' and not user.is_staff:
                    return None
                
                return user
        except User.DoesNotExist:
            # User doesn't exist in this schema
            return None
        
        return None
