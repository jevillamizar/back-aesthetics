from django.db import models


class ClinicLanding(models.Model):
    clinic = models.OneToOneField('clinics.Clinic', on_delete=models.PROTECT, related_name='landing')

    headline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    primary_color = models.CharField(max_length=20, blank=True)
    logo = models.ImageField(upload_to='landing/', blank=True)
    hero_image = models.ImageField(upload_to='landing/', blank=True)

    trust_indicators = models.JSONField(
        default=list,
        blank=True,
        help_text='Array of objects: [{"icon":"clock","label":"15+ Años","sub":"Experiencia"}, …]',
    )

    whatsapp_phone = models.CharField(max_length=50, blank=True)
    booking_url = models.URLField(blank=True)

    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)

    address = models.CharField(max_length=255, blank=True)

    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Clinic Landing'
        verbose_name_plural = 'Clinic Landings'

    def __str__(self) -> str:
        return f"Landing - {self.clinic}"
