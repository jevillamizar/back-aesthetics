from django.db import models


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELED = 'CANCELED', 'Canceled'
        NO_SHOW = 'NO_SHOW', 'No show'

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

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)

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
