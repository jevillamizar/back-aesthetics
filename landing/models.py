from django.db import models


class ClinicLanding(models.Model):
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

    # Logo display options (logo image is now in Clinic model)
    show_name = models.BooleanField(default=True, help_text='Mostrar el nombre de la clínica en la landing')
    show_logo = models.BooleanField(default=True, help_text='Mostrar el logo de la clínica en la landing')

    hero_image = models.ImageField(upload_to='landing/', blank=True)
    hero_image_urls = models.JSONField(
        default=list,
        blank=True,
        help_text='Array of image URLs for hero carousel, e.g. ["https://...", "https://..."]',
    )

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

    about_title = models.CharField(max_length=255, blank=True, help_text='About section title')
    about_subtitle = models.CharField(max_length=255, blank=True, help_text='About section italic accent line')
    about_description = models.TextField(blank=True, help_text='About section body text (supports multiple paragraphs)')
    about_bullets = models.JSONField(
        default=list,
        blank=True,
        help_text='Array of strings: ["Dermatólogos certificados", "Tratamientos aprobados", …]',
    )
    about_image = models.ImageField(upload_to='landing/', blank=True, help_text='About section image')
    about_image_urls = models.JSONField(
        default=list,
        blank=True,
        help_text='Array of image URLs for about carousel',
    )
    about_badge_title = models.CharField(max_length=50, blank=True, help_text='Floating badge big text, e.g. "Top 1%"')
    about_badge_text = models.CharField(max_length=255, blank=True, help_text='Floating badge description')

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
        return f"Landing - {self.headline or 'Untitled'}"
