from django.core.cache import cache
from ..models import SMTPSettings
from ..constants import SMTP_SETTINGS_CACHE_KEY

def get_smtp_settings(force_reload=False):
    """
    Fetch SMTP settings from cache or DB.
    If force_reload=True, bypass cache and reload from DB.
    """
    if not force_reload:
        cached = cache.get(SMTP_SETTINGS_CACHE_KEY)
        if cached:
            return cached

    obj = SMTPSettings.objects.first()
    if not obj:
        return None

    settings = {
        "host": obj.host,
        "port": obj.port,
        "username": obj.username,
        "password": obj.password,
        "from_email": obj.from_email,
    }

    cache.set(SMTP_SETTINGS_CACHE_KEY, settings, timeout=None)
    return settings
