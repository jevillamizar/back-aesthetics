from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Clinic(TenantMixin):
    name = models.CharField(max_length=255, verbose_name='Nombre de la clínica')
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Información básica
    business_name = models.CharField(max_length=255, blank=True, verbose_name='Razón social')
    tax_id = models.CharField(max_length=50, blank=True, verbose_name='NIT')
    company_type = models.CharField(max_length=100, blank=True, verbose_name='Tipo de empresa')
    logo = models.ImageField(upload_to='clinic_logos/', blank=True, verbose_name='Logo')
    short_description = models.TextField(blank=True, verbose_name='Descripción corta')

    # Contacto
    phone = models.CharField(max_length=50, blank=True, verbose_name='Teléfono')
    whatsapp = models.CharField(max_length=50, blank=True, verbose_name='WhatsApp')
    email = models.EmailField(max_length=255, blank=True, verbose_name='Correo principal')
    address = models.CharField(max_length=255, blank=True, verbose_name='Dirección')
    city = models.CharField(max_length=100, blank=True, verbose_name='Ciudad')
    country = models.CharField(max_length=100, blank=True, verbose_name='País')

    # Funcionalidades configurables
    enable_medical_history = models.BooleanField(
        default=True,
        verbose_name='Habilitar Historia Clínica',
    )
    enable_consent = models.BooleanField(
        default=True,
        verbose_name='Habilitar Consentimiento Informado',
    )

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = 'Clinic'
        verbose_name_plural = 'Clinics'

    def __str__(self) -> str:
        return self.name


class Domain(DomainMixin):
    pass
