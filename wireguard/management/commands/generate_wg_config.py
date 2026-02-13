#!/usr/bin/env python
# wireguard/management/commands/generate_wg_config.py
"""
Management command to generate /etc/wireguard/wg0.conf from database.
Usage: sudo python manage.py generate_wg_config [--interface wg0] [--output /etc/wireguard/wg0.conf]
"""
import os
from django.core.management.base import BaseCommand, CommandError
from wireguard.models import WireGuardServer, WireGuardPeer


class Command(BaseCommand):
    help = 'Generate WireGuard interface configuration file from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interface',
            type=str,
            default='wg0',
            help='WireGuard interface name (default: wg0)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (default: /etc/wireguard/{interface}.conf)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print config without writing to file'
        )

    def handle(self, *args, **options):
        interface = options['interface']
        output_path = options['output'] or f'/etc/wireguard/{interface}.conf'
        dry_run = options['dry_run']

        # Get the server configuration
        server = WireGuardServer.objects.filter(is_active=True).first()
        if not server:
            raise CommandError('No active WireGuard server found in database')

        # Verify the interface matches
        if server.interface != interface:
            raise CommandError(
                f'Server interface is "{server.interface}", but "--interface {interface}" was specified. '
                f'Use "--interface {server.interface}" or update the server settings.'
            )

        # Generate config
        config = self.generate_config(server)

        if dry_run:
            self.stdout.write(self.style.SUCCESS('=== Generated WireGuard Config ===\n'))
            self.stdout.write(config)
            self.stdout.write(
                self.style.WARNING(
                    f'\n[DRY RUN] Would write to: {output_path}\n'
                    'Run without --dry-run to write the file.'
                )
            )
        else:
            # Check if we have write permissions
            try:
                # Create directory if needed
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Write config
                with open(output_path, 'w') as f:
                    f.write(config)
                
                # Set restrictive permissions (owner read/write only)
                os.chmod(output_path, 0o600)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Configuration written to: {output_path}')
                )
                self.stdout.write(
                    self.style.SUCCESS('./Successfully generated WireGuard config\n')
                )
                
                # Instructions
                self.stdout.write(self.style.WARNING('Next steps:'))
                self.stdout.write(f'1. Bring up the interface: sudo wg-quick up {interface}')
                self.stdout.write(f'2. Enable at boot: sudo systemctl enable wg-quick@{interface}')
                self.stdout.write(f'3. Check status: sudo wg show')
                
            except PermissionError:
                raise CommandError(
                    f'Permission denied writing to {output_path}. '
                    f'Run with sudo: sudo python manage.py generate_wg_config --output {output_path}'
                )
            except Exception as e:
                raise CommandError(f'Error writing config: {e}')

    @staticmethod
    def generate_config(server: WireGuardServer) -> str:
        """
        Generate WireGuard interface configuration.
        """
        # Get private key
        try:
            private_key = server.get_private_key()
        except Exception as e:
            raise CommandError(f'Failed to decrypt server private key: {e}')

        lines = [
            '[Interface]',
            f'Address = {server.server_address}',
            f'ListenPort = {server.port}',
            f'PrivateKey = {private_key}',
        ]

        # Add DNS if configured
        if server.dns:
            dns_servers = ', '.join([d.strip() for d in server.dns.split(',')])
            lines.append(f'DNS = {dns_servers}')

        # Add MTU if not default
        if server.mtu != 1420:
            lines.append(f'MTU = {server.mtu}')

        # Add peers
        peers = server.peers.filter(is_active=True)
        if peers.exists():
            lines.append('')
            lines.append('# Active Peers')
            lines.append('')
            
            for peer in peers:
                lines.append('[Peer]')
                lines.append(f'# {peer.name} ({peer.platform})')
                lines.append(f'PublicKey = {peer.public_key}')
                lines.append(f'AllowedIPs = {peer.allowed_ip}')
                
                if peer.persistent_keepalive:
                    lines.append(f'PersistentKeepalive = {peer.persistent_keepalive}')
                
                lines.append('')

        lines.append('# End of WireGuard configuration')
        
        return '\n'.join(lines)
