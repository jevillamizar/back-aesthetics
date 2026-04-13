from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Clinic(TenantMixin):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = 'Clinic'
        verbose_name_plural = 'Clinics'

    def __str__(self) -> str:
        return self.name


class Domain(DomainMixin):
    pass
