from django.db import models


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING     = 'PENDING',     'Pendiente'
        COMPLETED   = 'COMPLETED',   'Completada'
        CANCELED    = 'CANCELED',    'Cancelada'
        NO_SHOW     = 'NO_SHOW',     'No asistió'
        EXPIRED     = 'EXPIRED',     'Vencida'

    class AppointmentType(models.TextChoices):
        VALORACION  = 'VALORACION',  'Valoración'
        TRATAMIENTO = 'TRATAMIENTO', 'Tratamiento'

    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='appointments')
    doctor = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='appointments',
        null=True,
        blank=True,
    )
    treatment = models.ForeignKey(
        'treatments.Treatment',
        on_delete=models.PROTECT,
        related_name='appointments',
        null=True,
        blank=True,
    )

    appointment_type = models.CharField(
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.TRATAMIENTO,
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    google_event_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        indexes = [
            models.Index(fields=['starts_at']),
            models.Index(fields=['doctor', 'starts_at']),
            models.Index(fields=['patient', 'starts_at']),
            models.Index(fields=['treatment', 'starts_at']),
        ]

    def __str__(self) -> str:
        return f"{self.starts_at} - {self.patient}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH     = 'CASH',     'Efectivo'
        CARD     = 'CARD',     'Tarjeta'
        TRANSFER = 'TRANSFER', 'Transferencia'
        OTHER    = 'OTHER',    'Otro'

    class Status(models.TextChoices):
        PENDING  = 'PENDING',  'Pendiente'
        PAID     = 'PAID',     'Pagado'
        PARTIAL  = 'PARTIAL',  'Parcial'
        REFUNDED = 'REFUNDED', 'Reembolsado'

    appointment = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.CASCADE,
        related_name='payment',
    )
    amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    method  = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    status  = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes   = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self) -> str:
        return f"Pago #{self.id} – {self.appointment} ({self.status})"
