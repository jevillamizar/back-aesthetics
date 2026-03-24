from django.db import models


class ClinicLanding(models.Model):
    clinic = models.OneToOneField('clinics.Clinic', on_delete=models.PROTECT, related_name='landing')

    headline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    primary_color = models.CharField(max_length=20, blank=True, help_text='Main brand color, e.g. "#8B9E8B"')
    secondary_color = models.CharField(max_length=20, blank=True, help_text='Secondary/surface color, e.g. "#F5F5F3"')
    accent_color = models.CharField(max_length=20, blank=True, help_text='Accent highlight color, e.g. "#D4A574"')
    background_color = models.CharField(max_length=20, blank=True, help_text='Page background, e.g. "#F5F5F3"')
    text_color = models.CharField(max_length=20, blank=True, help_text='Main text color, e.g. "#2D2D2D"')
    font_heading = models.CharField(max_length=100, blank=True, help_text='Google Font name for titles, e.g. "Playfair Display"')
    font_body = models.CharField(max_length=100, blank=True, help_text='Google Font name for body text, e.g. "Inter"')
    font_accent = models.CharField(max_length=100, blank=True, help_text='Google Font name for decorative text, e.g. "Cormorant Garamond"')
    logo = models.ImageField(upload_to='landing/', blank=True)
    hero_image = models.ImageField(upload_to='landing/', blank=True)

    trust_indicators = models.JSONField(
        default=list,
        blank=True,
        help_text='Array of objects: [{"icon":"clock","label":"15+ Años","sub":"Experiencia"}, …]',
    )
    testimonials = models.JSONField(
        default=list,
        blank=True,
        help_text='Array: [{"name":"Sarah M.","treatment":"Botox","rating":5,"quote":"..."}]',
    )

    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
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
