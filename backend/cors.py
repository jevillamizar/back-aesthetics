from __future__ import annotations

import re

from django.conf import settings
from django.http import HttpResponse


class PublicCORSMiddleware:
    """CORS middleware for public and API endpoints.

    Scoped to `/public/` and `/api/` routes.
    Also handles tenant detection for proper clinic data retrieval.
    """

    _allowed_origin_re = re.compile(
        r"^https?://([a-z0-9-]+\.)*lvh\.me:5173$", re.IGNORECASE
    )

    _cors_prefixes = ('/public/', '/api/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract tenant from Host header for ALL routes, not just CORS routes
        self._set_tenant_from_host(request)

        if not any(request.path.startswith(p) for p in self._cors_prefixes):
            return self.get_response(request)

        origin = (request.headers.get('Origin') or '').strip()
        is_allowed = self._is_origin_allowed(origin)

        if request.method == 'OPTIONS':
            response = HttpResponse(status=200)
        else:
            response = self.get_response(request)

        if is_allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Vary'] = 'Origin'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'

        return response

    def _set_tenant_from_host(self, request):
        """Extract subdomain from Host and set request.clinic."""
        host = request.get_host()
        base_domain = getattr(settings, 'TENANT_BASE_DOMAIN', 'lvh.me')

        # Remove port from host for domain lookup
        host_no_port = host.split(':')[0] if host else host

        # Extract subdomain
        subdomain = None
        if host_no_port and host_no_port != base_domain:
            if host_no_port.endswith(f'.{base_domain}'):
                subdomain = host_no_port[:-(len(base_domain) + 1)]
            elif host_no_port.endswith(base_domain):
                subdomain = host_no_port[:-len(base_domain)].rstrip('.')

        request.subdomain = subdomain

        # Look up clinic if subdomain found
        if subdomain:
            try:
                from django.db import connection
                from clinics.models import Domain, Clinic

                # Ensure we're in public schema for Domain lookup
                original_schema = connection.schema_name
                if original_schema != 'public':
                    connection.set_schema_to_public()

                try:
                    # Try with host without port first
                    domain = Domain.objects.select_related('tenant').get(
                        domain=host_no_port, is_primary=True
                    )
                    request.clinic = domain.tenant
                except Domain.DoesNotExist:
                    # Try with subdomain pattern
                    try:
                        domain = Domain.objects.select_related('tenant').get(
                            domain=f'{subdomain}.{base_domain}', is_primary=True
                        )
                        request.clinic = domain.tenant
                    except Domain.DoesNotExist:
                        request.clinic = None
                finally:
                    # Restore original schema if needed
                    if original_schema != 'public' and connection.schema_name != original_schema:
                        connection.set_schema(original_schema)
            except Exception:
                request.clinic = None
        else:
            request.clinic = None

    def _is_origin_allowed(self, origin: str) -> bool:
        if not origin:
            return False

        if origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            return True

        return bool(self._allowed_origin_re.match(origin))
