from django.db import models


class Patient(models.Model):
    class DocumentType(models.TextChoices):
        CC  = 'CC',  'Cédula de Ciudadanía'
        CE  = 'CE',  'Cédula de Extranjería'
        TI  = 'TI',  'Tarjeta de Identidad'
        PP  = 'PP',  'Pasaporte'
        RC  = 'RC',  'Registro Civil'
        NIT = 'NIT', 'NIT'

    class Sex(models.TextChoices):
        M = 'M', 'Masculino'
        F = 'F', 'Femenino'
        O = 'O', 'Otro'

    document_type   = models.CharField(max_length=10, choices=DocumentType.choices, blank=True)
    document_number = models.CharField(max_length=50, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    sex  = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to='patients/photos/', null=True, blank=True)

    # Administrative data
    eps                      = models.CharField(max_length=150, blank=True)
    legal_guardian           = models.CharField(max_length=255, blank=True)
    emergency_contact_name   = models.CharField(max_length=255, blank=True)
    emergency_contact_phone  = models.CharField(max_length=50,  blank=True)
    emergency_contact_relation = models.CharField(max_length=100, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self) -> str:
        return f"{self.last_name}, {self.first_name}"
