from django.db import models
from django.core.cache import cache
from utils.crypto import CryptoService
from .constants import (
    SMTP_SETTINGS_CACHE_KEY,
    WG_ACTIVE_PEERS_CACHE_KEY,
    WG_SERVER_CACHE_KEY,
    WG_SERVER_CONFIG_CACHE_KEY_PATTERN,
)

import ipaddress
from django.core.exceptions import ValidationError

def validate_cidr(value):
    """Validate that the input is a valid IP/CIDR (IPv4 or IPv6)."""
    try:
        ipaddress.ip_interface(value)
    except ValueError:
        raise ValidationError("Enter a valid IP address with CIDR (e.g., 10.10.10.1/24)")

class SMTPSettings(models.Model):
    host = models.CharField(max_length=100)
    port = models.IntegerField()
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=255)  # Plain text now
    from_email = models.EmailField()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(SMTP_SETTINGS_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(SMTP_SETTINGS_CACHE_KEY)

    class Meta:
        verbose_name = "SMTP Setting"
        verbose_name_plural = "SMTP Settings"

        indexes = [
            models.Index(fields=['host']),
            models.Index(fields=['username']),
        ]


class WireGuardServer(models.Model):
    name = models.CharField(max_length=100, help_text='Server name (e.g., "Production VPN")')
    endpoint = models.CharField(max_length=255, help_text='Public endpoint (e.g., vpn.example.com:51820)')
    server_address = models.CharField(
        max_length=43,  # Max for IPv6 + CIDR
        help_text='Server VPN IP with subnet (e.g., 10.0.0.1/24)',
        validators=[validate_cidr]
    )
    private_key_encrypted = models.TextField(blank=True, default='', help_text='Server private key (encrypted)')
    public_key = models.CharField(max_length=255, blank=True, default='', help_text='Server public key')
    interface = models.CharField(max_length=10, default='wg0', help_text='Network interface name')
    uplink_interface = models.CharField(
        max_length=15,
        default="eth0",
        help_text="Interface used for NAT egress"
    )
    port = models.IntegerField(default=51820, help_text='UDP port for WireGuard')
    dns = models.CharField(
        max_length=255,
        default='8.8.8.8,8.8.4.4',
        help_text='Comma-separated DNS servers for clients'
    )
    allowed_ips = models.CharField(
        max_length=255,
        default='0.0.0.0/0',
        help_text='Default allowed IPs for new peers'
    )
    is_active = models.BooleanField(default=True, help_text='Set to False to disable this server')
    mtu = models.IntegerField(default=1420, help_text='MTU size for WireGuard interface')
    persistent_keepalive = models.IntegerField(default=25, help_text='Persistent keepalive interval (0 to disable)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WireGuard Server"
        verbose_name_plural = "WireGuard Servers"

    def __str__(self):
        return f"{self.name} ({self.endpoint})"

    def set_private_key(self, key: str):
        """Encrypt and store the server's private key."""
        self.private_key_encrypted = CryptoService.encrypt(key)

    def get_private_key(self) -> str:
        """Retrieve and decrypt the server's private key."""
        return CryptoService.decrypt(self.private_key_encrypted)

    def save(self, *args, **kwargs):
        import sys
        
        # Generate keys if they don't exist (new server or incomplete keys)
        # Check for missing or empty private key
        private_key_missing = not self.private_key_encrypted or self.private_key_encrypted.strip() in ('', '-')
        public_key_missing = not self.public_key or self.public_key.strip() in ('', '-')
        
        if private_key_missing or public_key_missing:
            from .services.wireguard import WireGuardService
            try:
                print(f"[DEBUG] Generating WireGuard keys for server: {self.name}", file=sys.stderr)
                private_key, public_key = WireGuardService.generate_keys()
                
                if not private_key or not public_key:
                    raise ValueError("Key generation returned empty values")
                
                print(f"[DEBUG] Generated keys - Private: {private_key[:20]}... Public: {public_key[:20]}...", file=sys.stderr)
                
                # Encrypt and store the private key
                self.public_key = public_key
                self.set_private_key(private_key)
                
                print(f"[DEBUG] Successfully stored encrypted keys for server {self.name}", file=sys.stderr)
                print(f"[DEBUG] encrypted_key length: {len(self.private_key_encrypted)}", file=sys.stderr)
                
            except Exception as e:
                print(f"[ERROR] Failed to generate WireGuard keys for {self.name}: {e}", file=sys.stderr)
                import traceback
                print(f"[TRACEBACK] {traceback.format_exc()}", file=sys.stderr)
                
                # Set placeholder values to allow save to proceed
                # User can manually regenerate keys later
                if not self.public_key:
                    self.public_key = "-"
                if not self.private_key_encrypted:
                    self.private_key_encrypted = "-"
        
        super().save(*args, **kwargs)
        
        # Invalidate caches when server config changes (non-blocking)
        try:
            cache.delete(WG_SERVER_CACHE_KEY)
            cache.delete(WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=self.id))
        except Exception as e:
            # Don't fail the save if cache invalidation fails
            print(f"[WARNING] Could not invalidate cache: {e}", file=sys.stderr)
        

    def delete(self, *args, **kwargs):
        # Invalidate caches when server is deleted (non-blocking)
        try:
            cache.delete(WG_SERVER_CACHE_KEY)
            cache.delete(WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=self.id))
            # Also invalidate active peers cache since they depend on server
            cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)
        except Exception as e:
            # Don't fail the delete if cache invalidation fails
            import sys
            print(f"Warning: Could not invalidate cache on delete: {e}", file=sys.stderr)
        super().delete(*args, **kwargs)

    @classmethod
    def get_default(cls):
        """
        Get the default (first active) server with caching.
        """
        cached = cache.get(WG_SERVER_CACHE_KEY)
        if cached:
            return cached

        server = cls.objects.filter(is_active=True).first()
        if server:
            cache.set(WG_SERVER_CACHE_KEY, server, timeout=None)
        return server

    def to_dict(self) -> dict:
        """
        Get server configuration as dictionary (cached).
        """
        cache_key = WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=self.id)
        cached = cache.get(cache_key)
        if cached:
            return cached

        config = {
            'id': self.id,
            'name': self.name,
            'endpoint': self.endpoint,
            'server_address': self.server_address,
            'public_key': self.public_key,
            'interface': self.interface,
            'port': self.port,
            'dns': self.dns,
            'allowed_ips': self.allowed_ips,
            'mtu': self.mtu,
            'persistent_keepalive': self.persistent_keepalive,
            'is_active': self.is_active,
        }
        cache.set(cache_key, config, timeout=None)
        return config

    class Meta:
        ordering = ['-created_at']
        verbose_name = "WireGuard Server"
        verbose_name_plural = "WireGuard Servers"

        indexes = [
            models.Index(fields=['endpoint']),
            models.Index(fields=['is_active']),
        ]

class WireGuardPeer(models.Model):
    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('windows', 'Windows'),
        ('linux', 'Linux'),
        ('macos', 'macOS'),
    ]
    
    name = models.CharField(max_length=100)
    email = models.EmailField()
    server = models.ForeignKey(WireGuardServer, on_delete=models.PROTECT, related_name='peers', null=True, blank=True, help_text='WireGuard server this peer connects to')
    public_key = models.CharField(max_length=255, blank=True)
    private_key_encrypted = models.TextField(blank=True)
    allowed_ip = models.GenericIPAddressField()
    is_active = models.BooleanField(default=True)
    allowed_ips = models.CharField(max_length=255, default='0.0.0.0/0', help_text='Comma-separated IPs allowed through tunnel')
    dns = models.CharField(max_length=255, default='8.8.8.8,8.8.4.4', help_text='Comma-separated DNS servers')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='linux')
    server_endpoint = models.CharField(max_length=255, blank=True, help_text='Override server endpoint (auto-populated from server)')
    qr_path = models.CharField(max_length=255, blank=True, null=True, help_text='Path to generated QR code')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.email})"

    def get_server(self):
        """Get the server for this peer, or the default server."""
        if self.server:
            return self.server
        return WireGuardServer.get_default()

    def get_endpoint(self):
        """Get the effective endpoint for this peer."""
        if self.server_endpoint:
            return self.server_endpoint
        server = self.get_server()
        return server.endpoint if server else 'vpn.example.com:51820'

    def get_dns(self):
        """Get the effective DNS for this peer."""
        if self.dns:
            return self.dns
        server = self.get_server()
        return server.dns if server else '8.8.8.8,8.8.4.4'

    def get_allowed_ips(self):
        """Get the effective allowed IPs for this peer."""
        if self.allowed_ips:
            return self.allowed_ips
        server = self.get_server()
        return server.allowed_ips if server else '0.0.0.0/0'

    def set_private_key(self, key: str):
        self.private_key_encrypted = CryptoService.encrypt(key)

    def get_private_key(self) -> str:
        return CryptoService.decrypt(self.private_key_encrypted)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    class Meta:
        verbose_name = "WireGuard Peer"
        verbose_name_plural = "WireGuard Peers"

        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['allowed_ip']),
            models.Index(fields=['is_active']),
        ]