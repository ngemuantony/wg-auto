from django.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError

import ipaddress

from utils.crypto import CryptoService
from .constants import (
    SMTP_SETTINGS_CACHE_KEY,
    WG_ACTIVE_PEERS_CACHE_KEY,
    WG_SERVER_CACHE_KEY,
    WG_SERVER_CONFIG_CACHE_KEY_PATTERN,
)


# ============================================================
# Validators
# ============================================================

def validate_cidr(value):
    """Validate that the input is a valid IP/CIDR (IPv4 or IPv6)."""
    try:
        ipaddress.ip_interface(value)
    except ValueError:
        raise ValidationError(
            "Enter a valid IP address with CIDR (e.g., 10.10.10.1/24)"
        )


# ============================================================
# SMTP Settings
# ============================================================

class SMTPSettings(models.Model):
    host = models.CharField(max_length=100)
    port = models.IntegerField()
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=255)  # Plain text
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
            models.Index(fields=["host"]),
            models.Index(fields=["username"]),
        ]


# ============================================================
# WireGuard Server
# ============================================================

class WireGuardServer(models.Model):
    name = models.CharField(max_length=100)
    endpoint = models.CharField(
        max_length=255,
        help_text="Public endpoint (e.g., vpn.example.com:51820)",
    )
    server_address = models.CharField(
        max_length=43,
        validators=[validate_cidr],
        help_text="Server VPN IP with subnet (e.g., 10.0.0.1/24)",
    )

    private_key_encrypted = models.TextField(
        blank=True,
        default="",
        help_text="Server private key (encrypted)",
    )
    public_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Server public key",
    )

    interface = models.CharField(max_length=10, default="wg0")
    uplink_interface = models.CharField(max_length=15, default="eth0")
    port = models.IntegerField(default=51820)

    dns = models.CharField(
        max_length=255,
        default="8.8.8.8,8.8.4.4",
    )
    allowed_ips = models.CharField(
        max_length=255,
        default="0.0.0.0/0",
    )

    is_active = models.BooleanField(default=True)
    mtu = models.IntegerField(default=1420)
    persistent_keepalive = models.IntegerField(default=25)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --------------------------------------------------------

    def __str__(self):
        return f"{self.name} ({self.endpoint})"

    # --------------------------------------------------------
    # Key management
    # --------------------------------------------------------

    def set_private_key(self, key: str):
        self.private_key_encrypted = CryptoService.encrypt(key)

    def get_private_key(self) -> str:
        return CryptoService.decrypt(self.private_key_encrypted)

    # --------------------------------------------------------
    # Save override (AUTO-GENERATES KEYS)
    # --------------------------------------------------------

    def save(self, *args, **kwargs):
        from .services.wireguard import WireGuardService

        private_key_missing = not self.private_key_encrypted
        public_key_missing = not self.public_key

        if private_key_missing or public_key_missing:
            try:
                private_key, public_key = WireGuardService.generate_keys()

                if not private_key or not public_key:
                    raise ValueError("WireGuard key generation returned empty values")

                self.public_key = public_key
                self.set_private_key(private_key)

            except Exception as exc:
                # ❌ NEVER save a server without valid keys
                raise RuntimeError(
                    f"Cannot save WireGuard server '{self.name}' without valid keys"
                ) from exc

        super().save(*args, **kwargs)

        # Cache invalidation (non-fatal)
        try:
            cache.delete(WG_SERVER_CACHE_KEY)
            cache.delete(
                WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=self.id)
            )
        except Exception:
            pass

    # --------------------------------------------------------

    @classmethod
    def get_default(cls):
        cached = cache.get(WG_SERVER_CACHE_KEY)
        if cached:
            return cached

        server = cls.objects.filter(is_active=True).first()
        if server:
            cache.set(WG_SERVER_CACHE_KEY, server, timeout=None)
        return server

    def to_dict(self) -> dict:
        cache_key = WG_SERVER_CONFIG_CACHE_KEY_PATTERN.format(server_id=self.id)
        cached = cache.get(cache_key)
        if cached:
            return cached

        config = {
            "id": self.id,
            "name": self.name,
            "endpoint": self.endpoint,
            "server_address": self.server_address,
            "public_key": self.public_key,
            "interface": self.interface,
            "port": self.port,
            "dns": self.dns,
            "allowed_ips": self.allowed_ips,
            "mtu": self.mtu,
            "persistent_keepalive": self.persistent_keepalive,
            "is_active": self.is_active,
        }

        cache.set(cache_key, config, timeout=None)
        return config

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WireGuard Server"
        verbose_name_plural = "WireGuard Servers"
        indexes = [
            models.Index(fields=["endpoint"]),
            models.Index(fields=["is_active"]),
        ]


# ============================================================
# WireGuard Peer
# ============================================================

class WireGuardPeer(models.Model):
    PLATFORM_CHOICES = [
        ("android", "Android"),
        ("ios", "iOS"),
        ("windows", "Windows"),
        ("linux", "Linux"),
        ("macos", "macOS"),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField()

    server = models.ForeignKey(
        WireGuardServer,
        on_delete=models.PROTECT,
        related_name="peers",
        null=True,
        blank=True,
    )

    public_key = models.CharField(max_length=255, blank=True)
    private_key_encrypted = models.TextField(blank=True)

    allowed_ip = models.GenericIPAddressField()
    is_active = models.BooleanField(default=True)

    allowed_ips = models.CharField(
        max_length=255,
        default="0.0.0.0/0",
    )
    dns = models.CharField(
        max_length=255,
        default="8.8.8.8,8.8.4.4",
    )

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        default="linux",
    )

    server_endpoint = models.CharField(max_length=255, blank=True)
    qr_path = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --------------------------------------------------------

    def __str__(self):
        return f"{self.name} ({self.email})"

    def get_server(self):
        return self.server or WireGuardServer.get_default()

    def get_endpoint(self):
        return self.server_endpoint or (
            self.get_server().endpoint if self.get_server() else ""
        )

    def get_dns(self):
        return self.dns or (
            self.get_server().dns if self.get_server() else ""
        )

    def get_allowed_ips(self):
        return self.allowed_ips or (
            self.get_server().allowed_ips if self.get_server() else ""
        )

    # --------------------------------------------------------
    # Key helpers
    # --------------------------------------------------------

    def set_private_key(self, key: str):
        self.private_key_encrypted = CryptoService.encrypt(key)

    def get_private_key(self) -> str:
        return CryptoService.decrypt(self.private_key_encrypted)

    # --------------------------------------------------------

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WireGuard Peer"
        verbose_name_plural = "WireGuard Peers"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["allowed_ip"]),
            models.Index(fields=["is_active"]),
        ]
