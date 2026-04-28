from django.contrib import admin

from .models import GoogleCalendarToken


@admin.register(GoogleCalendarToken)
class GoogleCalendarTokenAdmin(admin.ModelAdmin):
    list_display = ('calendar_id', 'connected_at', 'updated_at')
    readonly_fields = ('connected_at', 'updated_at', 'scopes')
