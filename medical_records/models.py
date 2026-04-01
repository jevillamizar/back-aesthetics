from django.db import models


class MedicalRecord(models.Model):
    patient = models.ForeignKey('patients.Patient', on_delete=models.PROTECT, related_name='medical_records')
    doctor = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='medical_records')
    appointment = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.PROTECT,
        related_name='medical_record',
        null=True,
        blank=True,
    )

    treatments = models.ManyToManyField(
        'treatments.Treatment',
        through='MedicalRecordTreatment',
        related_name='medical_records',
        blank=True,
    )

    chief_complaint = models.CharField(max_length=255, blank=True)
    diagnosis = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Medical Record'
        verbose_name_plural = 'Medical Records'
        indexes = [
            models.Index(fields=['patient', 'created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.patient} - {self.created_at}"


class MedicalRecordTreatment(models.Model):
    medical_record = models.ForeignKey('medical_records.MedicalRecord', on_delete=models.CASCADE, related_name='treatment_items')
    treatment = models.ForeignKey('treatments.Treatment', on_delete=models.PROTECT, related_name='medical_record_treatments')

    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Medical Record Treatment'
        verbose_name_plural = 'Medical Record Treatments'
        indexes = [
            models.Index(fields=['medical_record']),
            models.Index(fields=['treatment']),
        ]

    def __str__(self) -> str:
        return f"{self.treatment} x{self.quantity}"
