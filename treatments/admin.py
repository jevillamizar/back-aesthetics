from django.contrib import admin

from .models import Treatment


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'slug', 'duration_minutes', 'price', 'is_active', 'created_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'slug')
