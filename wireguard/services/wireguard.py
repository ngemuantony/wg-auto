import os
import subprocess
from django.conf import settings
from django.core.cache import cache

from wireguard.models import WireGuardPeer
from wireguard.constants import WG_ACTIVE_PEERS_CACHE_KEY
from .qr import generate_qr


# ============================================================
# SYSTEM BINARIES (ABSOLUTE PATHS — OPTION A)
# ============================================================

WG_BIN = "/usr/bin/wg"


# ============================================================
# ACTIVE PEERS CACHE
# ============================================================

def get_active_peers():
    """
    Cached list of active WireGuard peers.
    Used by config generation and sync logic.
    """
    peers = cache.get(WG_ACTIVE_PEERS_CACHE_KEY)
    if peers:
        return peers

    qs = (
        WireGuardPeer.objects
        .filter(is_active=True)
        .select_related("server")
    )

    peers = []
    for peer in qs:
        server = peer.get_server()
        peers.append({
            "id": peer.id,
            "name": peer.name,
            "email": peer.email,
            "public_key": peer.public_key,
            "private_key": peer.get_private_key(),
            "allowed_ip": peer.allowed_ip,
            "server_id": peer.server_id,
            "server_endpoint": peer.get_endpoint(),
            "platform": peer.platform,
        })

    cache.set(WG_ACTIVE_PEERS_CACHE_KEY, peers, timeout=None)
    return peers


# ============================================================
# WIREGUARD RUNTIME SERVICE (NO SUDO, NO RESTARTS)
# ============================================================

class WireGuardService:
    """
    Runtime WireGuard operations.

    IMPORTANT:
    - Uses absolute binary paths
    - Never calls sudo
    - Never restarts the interface
    - Safe for Celery + systemd
    """

    @staticmethod
    def generate_keys(timeout: int = 5) -> tuple[str, str]:
        """
        Generate WireGuard private & public keys using system wg binary.

        Returns:
            (private_key, public_key)
        """
        if os.name == "nt":
            raise RuntimeError("WireGuard is not supported on Windows")

        try:
            # Generate private key
            private_key_proc = subprocess.run(
                [WG_BIN, "genkey"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )

            private_key = private_key_proc.stdout.strip()
            if not private_key:
                raise RuntimeError("Empty private key returned")

            # Generate public key
            public_key_proc = subprocess.run(
                [WG_BIN, "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )

            public_key = public_key_proc.stdout.strip()
            if not public_key:
                raise RuntimeError("Empty public key returned")

            return private_key, public_key

        except subprocess.TimeoutExpired:
            raise RuntimeError("WireGuard key generation timed out")

        except FileNotFoundError:
            raise RuntimeError(
                "WireGuard binary not found at /usr/bin/wg. "
                "Install with: apt install wireguard-tools"
            )

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else "unknown error"
            raise RuntimeError(f"WireGuard key generation failed: {stderr}")

        except Exception as e:
            raise RuntimeError(f"Unexpected WireGuard error: {e}") from e

    # --------------------------------------------------------

    @staticmethod
    def _run(cmd: list[str]):
        """
        Execute WireGuard command safely.
        No-op on Windows.
        """
        if os.name == "nt":
            return

        subprocess.run(cmd, check=True)

    # --------------------------------------------------------

    @classmethod
    def add_peer(cls, peer: WireGuardPeer):
        """
        Inject peer into a live WireGuard interface.
        """
        cls._run([
            WG_BIN,
            "set",
            settings.WIREGUARD_INTERFACE,
            "peer",
            peer.public_key,
            "allowed-ips",
            peer.allowed_ip,
        ])

        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    # --------------------------------------------------------

    @classmethod
    def remove_peer(cls, peer: WireGuardPeer):
        """
        Remove peer from a live WireGuard interface.
        """
        cls._run([
            WG_BIN,
            "set",
            settings.WIREGUARD_INTERFACE,
            "peer",
            peer.public_key,
            "remove",
        ])

        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)
