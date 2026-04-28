from django.db import models


class GoogleCalendarToken(models.Model):
    """
    Stores the OAuth2 credentials for a tenant's connected Google Calendar.
    One record per tenant (enforced by the tenant schema).
    """
    calendar_id    = models.CharField(max_length=255, blank=True, help_text='Google Calendar ID (email or calendar ID)')
    access_token   = models.TextField()
    refresh_token  = models.TextField()
    token_expiry   = models.DateTimeField(null=True, blank=True)
    scopes         = models.TextField(blank=True)
    connected_at   = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Google Calendar Token'
        verbose_name_plural = 'Google Calendar Tokens'

    def __str__(self) -> str:
        return f"GCal token — {self.calendar_id or 'not configured'}"
