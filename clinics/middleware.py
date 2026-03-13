from __future__ import annotations

from dataclasses import dataclass
from threading import local

from django.http import Http404

from .models import Clinic


_state = local()


@dataclass(frozen=True)
class TenantInfo:
    clinic: Clinic | None
    subdomain: str | None


def get_current_tenant() -> TenantInfo:
    return getattr(_state, 'tenant', TenantInfo(clinic=None, subdomain=None))


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        host = request.get_host().split(':')[0].lower()
        base_domain = getattr(settings, 'TENANT_BASE_DOMAIN', 'lvh.me').lower()

        clinic = None
        subdomain = None

        if host.endswith(base_domain) and host != base_domain:
            suffix = f'.{base_domain}'
            if host.endswith(suffix):
                subdomain = host[: -len(suffix)]
                if subdomain:
                    clinic = Clinic.objects.filter(slug=subdomain, is_active=True).first()
                    if clinic is None:
                        raise Http404('Clinic not found')

        request.clinic = clinic
        request.subdomain = subdomain
        _state.tenant = TenantInfo(clinic=clinic, subdomain=subdomain)

        return self.get_response(request)
