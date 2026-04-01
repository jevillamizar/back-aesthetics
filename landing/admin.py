from django.contrib import admin

from .models import ClinicLanding


@admin.register(ClinicLanding)
class ClinicLandingAdmin(admin.ModelAdmin):
    list_display = ('headline', 'is_published', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('headline',)
