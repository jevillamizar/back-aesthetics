from django.contrib import admin

from .models import Treatment


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'clinic', 'duration_minutes', 'price', 'is_active', 'created_at')
    list_filter = ('clinic', 'is_active')
    search_fields = ('name',)
