from django.db import models


class Treatment(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, blank=True, help_text='Grouping label shown as tab in the landing, e.g. "Tratamientos Faciales"')
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Treatment'
        verbose_name_plural = 'Treatments'
        constraints = [
            models.UniqueConstraint(fields=['slug'], name='uniq_treatment_slug'),
        ]
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
        ]

    def __str__(self) -> str:
        return self.name
