# wireguard/signals.py
import sys
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import WireGuardPeer, WireGuardServer
from .models import SMTPSettings
from .constants import SMTP_SETTINGS_CACHE_KEY
from .constants import WG_ACTIVE_PEERS_CACHE_KEY, WG_SERVER_CACHE_KEY

@receiver(post_save, sender=WireGuardPeer)
def trigger_onboarding(sender, instance, created, **kwargs):
    """Trigger onboarding for newly created peers OR peers without keys."""
    # Trigger onboarding if this is a NEW peer, OR if peer exists but has no keys
    needs_onboarding = created or (not instance.public_key or instance.public_key.strip() in ('', '-'))
    
    if needs_onboarding:
        from .tasks import onboard_peer
        try:
            print(f"[SIGNAL] Triggering onboarding for peer {instance.name} (created={created})", file=sys.stderr)
            onboard_peer.delay(instance.id)
        except Exception as e:
            print(f"[SIGNAL] Warning: Could not trigger onboarding task: {e}", file=sys.stderr)


@receiver(post_save, sender=WireGuardPeer)
def trigger_peer_injection(sender, instance, created, **kwargs):
    """
    When a peer is UPDATED (not created), inject it into the live WireGuard interface.
    For new peers, onboarding task generates keys first, then config sync handles injection.
    """
    # Skip injection for newly created peers - let onboarding generate keys first
    if created:
        print(f"[SIGNAL] New peer {instance.name} created - skipping injection until keys generated", file=sys.stderr)
        return
    
    # Only inject on updates (when keys and config already exist)
    from .tasks import inject_peer_live
    try:
        inject_peer_live.delay(instance.id)
        print(f"[SIGNAL] Triggered peer injection for {instance.name}", file=sys.stderr)
    except Exception as e:
        print(f"[SIGNAL] Warning: Could not trigger peer injection: {e}", file=sys.stderr)


@receiver(post_delete, sender=WireGuardPeer)
def trigger_peer_removal(sender, instance, **kwargs):
    """When a peer is deleted, remove it from the live interface."""
    from .tasks import inject_peer_live
    try:
        # Mark as inactive and trigger removal
        instance.is_active = False
        inject_peer_live.delay(instance.id)
    except Exception as e:
        import sys
        print(f"[SIGNAL] Warning: Could not trigger peer removal: {e}", file=sys.stderr)


@receiver(post_save, sender=WireGuardServer)
def invalidate_server_cache(sender, instance, **kwargs):
    """Invalidate cache when server configuration changes."""
    try:
        cache.delete(WG_SERVER_CACHE_KEY)
        # Also invalidate active peers cache since they depend on server config
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)
    except Exception as e:
        # Don't fail the operation if cache invalidation fails
        import sys
        print(f"Warning: Could not invalidate server cache: {e}", file=sys.stderr)


@receiver(post_save, sender=WireGuardServer)
def sync_wg_config_on_save(sender, instance, **kwargs):
    """When server configuration is saved, regenerate wg0.conf file."""
    from .tasks import sync_wg_config
    try:
        # Trigger async task to regenerate config without blocking
        sync_wg_config.delay(instance.id)
    except Exception as e:
        import sys
        print(f"[SIGNAL] Warning: Could not trigger config sync: {e}", file=sys.stderr)


@receiver(post_delete, sender=WireGuardServer)
def invalidate_server_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when server is deleted."""
    try:
        cache.delete(WG_SERVER_CACHE_KEY)
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)
    except Exception as e:
        # Don't fail the operation if cache invalidation fails
        import sys
        print(f"Warning: Could not invalidate server cache on delete: {e}", file=sys.stderr)

@receiver(post_save, sender=SMTPSettings)
@receiver(post_delete, sender=SMTPSettings)
def invalidate_smtp_cache(sender, instance, **kwargs):
    from django.core.cache import cache
    cache.delete(SMTP_SETTINGS_CACHE_KEY)