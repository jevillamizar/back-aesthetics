from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('starts_at', 'ends_at', 'status', 'doctor', 'patient', 'treatment', 'created_at')
    list_filter = ('status', 'doctor', 'treatment')
    search_fields = ('patient__first_name', 'patient__last_name', 'doctor__email', 'treatment__name')
