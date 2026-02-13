# wireguard/services/wireguard.py
import os
import subprocess
import base64
from django.conf import settings
from django.core.cache import cache
from wireguard.models import WireGuardPeer
from wireguard.constants import WG_ACTIVE_PEERS_CACHE_KEY
from .qr import generate_qr


def get_active_peers():
    """
    Cached list of active WireGuard peers.
    Used by config generation and sync logic.
    Includes server configuration if available.
    """
    peers = cache.get(WG_ACTIVE_PEERS_CACHE_KEY)
    if peers:
        return peers

    qs = WireGuardPeer.objects.filter(is_active=True).select_related('server')

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


class WireGuardService:
    """
    Runtime WireGuard operations.
    This class NEVER restarts the interface.
    """

    @staticmethod
    def generate_keys() -> tuple[str, str]:
        """
        Generate WireGuard private and public keys using system wg command.
        Uses sudo to escalate privileges (must be configured in /etc/sudoers first).
        Returns: (private_key, public_key)
        """
        try:
            # Generate private key using 'wg genkey'
            private_key_output = subprocess.run(
                ["sudo", "wg", "genkey"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=10
            )
            private_key = private_key_output.stdout.strip()

            # Generate public key from private key using 'wg pubkey'
            public_key_output = subprocess.run(
                ["sudo", "wg", "pubkey"],
                input=private_key,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=10
            )
            public_key = public_key_output.stdout.strip()

            if not private_key or not public_key:
                raise ValueError("Key generation returned empty values")

            return private_key, public_key
            
        except subprocess.CalledProcessError as e:
            import sys
            error_msg = e.stderr if e.stderr else str(e)
            print(f"[KEY_GEN] Error running 'wg' command: {error_msg}", file=sys.stderr)
            print(f"[KEY_GEN] Make sure /etc/sudoers is configured. Run: sudo bash scripts/setup-sudoers.sh <username>", file=sys.stderr)
            raise RuntimeError(f"Failed to generate WireGuard keys with wg command: {error_msg}")
            
        except FileNotFoundError:
            import sys
            print(f"[KEY_GEN] 'wg' command not found. Is WireGuard installed?", file=sys.stderr)
            print(f"[KEY_GEN] Install with: sudo apt install wireguard", file=sys.stderr)
            raise RuntimeError("WireGuard 'wg' command not found on system")
            
        except subprocess.TimeoutExpired:
            import sys
            print(f"[KEY_GEN] 'wg' command timeout", file=sys.stderr)
            raise RuntimeError("WireGuard key generation timed out")
            
        except Exception as e:
            import sys
            print(f"[KEY_GEN] Unexpected error: {e}", file=sys.stderr)
            raise RuntimeError(f"Failed to generate WireGuard keys: {e}")

    @staticmethod
    def _run(cmd: list[str]):
        """
        Execute wg command safely.
        Disabled on Windows.
        """
        if os.name == "nt":
            # Windows dev mode: no-op
            return

        subprocess.run(cmd, check=True)

    @classmethod
    def add_peer(cls, peer: WireGuardPeer):
        """
        Inject peer into a live WireGuard interface.
        """
        cls._run([
            "wg",
            "set",
            settings.WIREGUARD_INTERFACE,
            "peer",
            peer.public_key,
            "allowed-ips",
            peer.allowed_ip,
        ])

        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)

    @classmethod
    def remove_peer(cls, peer: WireGuardPeer):
        """
        Remove peer from a live WireGuard interface.
        """
        cls._run([
            "wg",
            "set",
            settings.WIREGUARD_INTERFACE,
            "peer",
            peer.public_key,
            "remove",
        ])

        cache.delete(WG_ACTIVE_PEERS_CACHE_KEY)
