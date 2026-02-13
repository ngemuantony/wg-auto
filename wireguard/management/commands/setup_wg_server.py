#!/usr/bin/env python
# wireguard/management/commands/setup_wg_server.py
"""
Management command to create or update WireGuard server configuration.
Usage: python manage.py setup_wg_server
"""
from django.core.management.base import BaseCommand
from wireguard.models import WireGuardServer
from wireguard.services.wireguard import WireGuardService
import json


class Command(BaseCommand):
    help = 'Setup or update WireGuard server configuration'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, help='Server name')
        parser.add_argument('--endpoint', type=str, help='Public endpoint (e.g., vpn.example.com:51820)')
        parser.add_argument('--address', type=str, help='Server VPN address (e.g., 10.0.0.1/24)')
        parser.add_argument('--interface', type=str, default='wg0', help='Network interface')
        parser.add_argument('--port', type=int, default=51820, help='UDP port')
        parser.add_argument('--dns', type=str, default='8.8.8.8,8.8.4.4', help='DNS servers (comma-separated)')
        parser.add_argument('--interactive', action='store_true', help='Interactive mode')

    def handle(self, *args, **options):
        if options['interactive']:
            self.interactive_setup()
        else:
            self.programmatic_setup(options)

    def interactive_setup(self):
        """Interactive server setup wizard."""
        self.stdout.write(self.style.SUCCESS('=== WireGuard Server Setup ===\n'))

        # Check if server already exists
        server = WireGuardServer.objects.filter(is_active=True).first()
        if server:
            self.stdout.write(f"Found existing server: {server.name}")
            update = input("Update this server? (y/n): ").lower() == 'y'
            if not update:
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
        else:
            server = None

        # Get user inputs
        name = input("Server name (e.g., 'Production VPN'): ").strip() or "WireGuard Server"
        endpoint = input("Public endpoint (e.g., vpn.example.com:51820): ").strip() or "vpn.example.com:51820"
        address = input("Server VPN address (e.g., 10.0.0.1/24): ").strip() or "10.0.0.1/24"
        interface = input("Network interface [wg0]: ").strip() or "wg0"
        port = int(input("UDP port [51820]: ").strip() or "51820")
        dns = input("DNS servers [8.8.8.8,8.8.4.4]: ").strip() or "8.8.8.8,8.8.4.4"
        mtu = int(input("MTU size [1420]: ").strip() or "1420")

        # Generate keys
        self.stdout.write("\nGenerating WireGuard keys...")
        private_key, public_key = WireGuardService.generate_keys()
        self.stdout.write(self.style.SUCCESS("✓ Keys generated"))

        # Create or update server
        if server:
            server.name = name
            server.endpoint = endpoint
            server.server_address = address
            server.interface = interface
            server.port = port
            server.dns = dns
            server.mtu = mtu
            server.public_key = public_key
            server.set_private_key(private_key)
            server.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Updated server: {server.name}"))
        else:
            server = WireGuardServer.objects.create(
                name=name,
                endpoint=endpoint,
                server_address=address,
                interface=interface,
                port=port,
                dns=dns,
                mtu=mtu,
                public_key=public_key,
            )
            server.set_private_key(private_key)
            server.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Created server: {server.name}"))

        # Display summary
        self.stdout.write(self.style.SUCCESS('\n=== Server Configuration ==='))
        self.stdout.write(json.dumps({
            'id': server.id,
            'name': server.name,
            'endpoint': server.endpoint,
            'address': server.server_address,
            'interface': server.interface,
            'port': server.port,
            'dns': server.dns,
            'mtu': server.mtu,
            'public_key': server.public_key[:20] + '...',
        }, indent=2))

    def programmatic_setup(self, options):
        """Programmatic server setup from command arguments."""
        name = options.get('name', 'WireGuard Server').strip()
        endpoint = options.get('endpoint', 'vpn.example.com:51820').strip()
        address = options.get('address', '10.0.0.1/24').strip()
        interface = options.get('interface', 'wg0').strip()
        port = options.get('port', 51820)
        dns = options.get('dns', '8.8.8.8,8.8.4.4').strip()

        # Generate keys
        self.stdout.write("Generating WireGuard keys...")
        private_key, public_key = WireGuardService.generate_keys()

        # Create or update server
        server, created = WireGuardServer.objects.update_or_create(
            is_active=True,
            defaults={
                'name': name,
                'endpoint': endpoint,
                'server_address': address,
                'interface': interface,
                'port': port,
                'dns': dns,
                'public_key': public_key,
            }
        )
        server.set_private_key(private_key)
        server.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"✓ {action} server: {server.name}"))
        self.stdout.write(self.style.SUCCESS(f"  Endpoint: {server.endpoint}"))
        self.stdout.write(self.style.SUCCESS(f"  Address: {server.server_address}"))
