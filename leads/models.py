from django.db import models


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW        = 'NEW',        'Nuevo'
        CONTACTED  = 'CONTACTED',  'Contactado'
        CONVERTED  = 'CONVERTED',  'Convertido'
        LOST       = 'LOST',       'Perdido'

    class Source(models.TextChoices):
        LANDING    = 'LANDING',    'Landing page'
        WHATSAPP   = 'WHATSAPP',   'WhatsApp'
        REFERRAL   = 'REFERRAL',   'Referido'
        OTHER      = 'OTHER',      'Otro'

    first_name     = models.CharField(max_length=150)
    last_name      = models.CharField(max_length=150)
    phone          = models.CharField(max_length=50, blank=True)
    email          = models.EmailField(blank=True)
    interest_notes = models.TextField(blank=True, help_text='Tratamiento de interés o motivo de consulta')
    source         = models.CharField(max_length=20, choices=Source.choices, default=Source.LANDING)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    appointment    = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lead',
    )
    patient        = models.ForeignKey(
        'patients.Patient',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads',
    )
    notes          = models.TextField(blank=True, help_text='Notas internas del equipo')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['email']),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.status})"
