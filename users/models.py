from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El usuario debe tener un email")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        DOCTOR = 'DOCTOR', 'Doctor'
        CLIENT = 'CLIENT', 'Client'

    class DocType(models.TextChoices):
        CC = 'CC', 'Cédula de ciudadanía'
        CE = 'CE', 'Cédula de extranjería'
        PP = 'PP', 'Pasaporte'
        TP = 'TP', 'Tarjeta profesional'

    class RethusStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        SUSPENDED = 'SUSPENDED', 'Suspendido'

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMIN)

    # Identification
    document_type = models.CharField(max_length=5, choices=DocType.choices, blank=True, default='CC')
    document_number = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # Professional info
    profession = models.CharField(max_length=100, blank=True)
    specialty = models.CharField(max_length=100, blank=True)
    university = models.CharField(max_length=150, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)

    # ReTHUS
    rethus_number = models.CharField(max_length=50, blank=True)
    rethus_status = models.CharField(max_length=15, choices=RethusStatus.choices, default=RethusStatus.ACTIVE, blank=True)
    certifying_entity = models.CharField(max_length=150, blank=True)

    # Public profile (landing page)
    bio = models.TextField(blank=True, help_text='Sobre mí — visible en landing page (100-500 chars)')
    photo = models.ImageField(upload_to='doctors/', blank=True, help_text='Foto de perfil del médico')

    # Responsibility
    professional_seal = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email