import subprocess
import sys
from celery import shared_task
from django.conf import settings
from .models import WireGuardPeer, WireGuardServer
from .services.onboarding import onboard, generate_server_config


# ============================================================
# Peer Onboarding Task
# ============================================================

@shared_task(bind=True, max_retries=3)
def onboard_peer(self, peer_id: int):
    try:
        onboard(peer_id)
        print(f"[ONBOARD] Completed for peer {peer_id}", file=sys.stderr)

        peer = WireGuardPeer.objects.get(id=peer_id)
        server = peer.server or peer.get_server()

        if server:
            sync_wg_config.delay(server.id)
            inject_peer_live.delay(peer.id)

        return {"status": "success", "peer_id": peer_id}

    except WireGuardPeer.DoesNotExist:
        return {"status": "error", "message": "Peer not found"}

    except Exception as e:
        print(f"[ONBOARD] ERROR: {e}", file=sys.stderr)
        raise self.retry(exc=e, countdown=10)


# ============================================================
# Server Configuration Sync Task
# ============================================================

@shared_task(bind=True, max_retries=2)
def sync_wg_config(self, server_id: int):
    try:
        server = WireGuardServer.objects.get(id=server_id)
        private_key = server.get_private_key()
        config_content = generate_server_config(server, private_key)

        config_path = f"/etc/wireguard/{server.interface}.conf"

        # Write config using sudo tee (NO temp files)
        proc = subprocess.run(
            ["sudo", "-n", "tee", config_path],
            input=config_content,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if proc.returncode != 0:
            raise PermissionError(proc.stderr.strip())

        subprocess.run(
            ["sudo", "-n", "chmod", "600", config_path],
            check=True,
        )

        print(f"[WG_SYNC] Config written: {config_path}", file=sys.stderr)
        return {"status": "success", "server": server.interface}

    except WireGuardServer.DoesNotExist:
        return {"status": "error", "message": "Server not found"}

    except PermissionError as e:
        print(f"[WG_SYNC] PERMISSION ERROR: {e}", file=sys.stderr)
        # Do NOT retry forever on sudo errors
        raise

    except Exception as e:
        print(f"[WG_SYNC] ERROR: {e}", file=sys.stderr)
        raise self.retry(exc=e, countdown=10)


# ============================================================
# Live Peer Injection Task
# ============================================================

@shared_task(bind=True, max_retries=2)
def inject_peer_live(self, peer_id: int):
    try:
        peer = WireGuardPeer.objects.get(id=peer_id)
        server = peer.get_server()

        if not server or not server.is_active:
            return {"status": "skipped", "reason": "No active server"}

        if not peer.public_key or peer.public_key.strip() in ("", "-"):
            print(f"[WG_INJECT] Public key missing for {peer.name}", file=sys.stderr)
            return {"status": "skipped", "reason": "No public key"}

        if peer.is_active:
            cmd = [
                "sudo", "-n", "wg", "set", server.interface,
                "peer", peer.public_key,
                "allowed-ips", peer.allowed_ip,
            ]

            if server.persistent_keepalive:
                cmd += ["persistent-keepalive", str(server.persistent_keepalive)]

            action = "inject"

        else:
            cmd = [
                "sudo", "-n", "wg", "set", server.interface,
                "peer", peer.public_key,
                "remove",
            ]
            action = "remove"

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0:
            raise PermissionError(proc.stderr.strip())

        print(
            f"[WG_INJECT] Peer {peer.name} {action}ed on {server.interface}",
            file=sys.stderr,
        )

        return {"status": "success", "peer": peer.name}

    except WireGuardPeer.DoesNotExist:
        return {"status": "error", "message": "Peer not found"}

    except PermissionError as e:
        print(f"[WG_INJECT] PERMISSION ERROR: {e}", file=sys.stderr)
        raise

    except Exception as e:
        print(f"[WG_INJECT] ERROR: {e}", file=sys.stderr)
        raise self.retry(exc=e, countdown=5)
