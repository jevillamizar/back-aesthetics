from __future__ import annotations

import re

from django.http import HttpResponse


class PublicCORSMiddleware:
    """CORS middleware for public and API endpoints.

    Scoped to `/public/` and `/api/` routes.
    """

    _allowed_origin_re = re.compile(
        r"^https?://([a-z0-9-]+\.)*lvh\.me:5173$", re.IGNORECASE
    )

    _cors_prefixes = ('/public/', '/api/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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

    def _is_origin_allowed(self, origin: str) -> bool:
        if not origin:
            return False

        if origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            return True

        return bool(self._allowed_origin_re.match(origin))
