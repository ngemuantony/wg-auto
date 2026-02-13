# wireguard/services/server.py
"""
WireGuard Server management service with caching.
"""
from django.core.cache import cache
from django.utils import timezone
from wireguard.models import WireGuardServer
from wireguard.constants import WG_SERVER_CACHE_KEY, WG_SERVER_CONFIG_CACHE_KEY_PATTERN


class WireGuardServerService:
    """
    Cached server configuration and management.
    All operations use cache for performance.
    """

    @staticmethod
    def get_default_server() -> WireGuardServer | None:
        """
        Get the default (first active) WireGuard server.
        Results are cached.
        """
        return WireGuardServer.get_default()

    @staticmethod
    def get_server_config(server_id: int) -> dict | None:
        """
        Get server configuration as dictionary.
        Results are cached.
        """
        try:
            server = WireGuardServer.objects.get(id=server_id)
            return server.to_dict()
        except WireGuardServer.DoesNotExist:
            return None

    @staticmethod
    def get_all_servers() -> list[WireGuardServer]:
        """
        Get all active servers (not cached - rare operation).
        """
        return list(WireGuardServer.objects.filter(is_active=True))

    @staticmethod
    def invalidate_cache(server_id: int = None):
        """
        Manually invalidate server cache.
        If server_id is provided, only invalidates that server's cache.
        Otherwise invalidates all server caches.
        """
        if server_id:
            cache.delete(WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=server_id))
        else:
            cache.delete(WG_SERVER_CACHE_KEY)
            # Invalidate all server configs (limited to ~100 servers)
            for server in WireGuardServer.objects.all():
                cache.delete(WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=server.id))

    @staticmethod
    def get_server_stats(server: WireGuardServer) -> dict:
        """
        Get server statistics (active peers count, etc).
        """
        active_peers = server.peers.filter(is_active=True).count()
        inactive_peers = server.peers.filter(is_active=False).count()

        return {
            'server_id': server.id,
            'server_name': server.name,
            'endpoint': server.endpoint,
            'active_peers': active_peers,
            'inactive_peers': inactive_peers,
            'total_peers': active_peers + inactive_peers,
            'interface': server.interface,
            'port': server.port,
            'last_updated': server.updated_at.isoformat() if server.updated_at else None,
        }
