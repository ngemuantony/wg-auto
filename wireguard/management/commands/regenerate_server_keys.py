from django.core.management.base import BaseCommand, CommandError
from wireguard.models import WireGuardServer
from wireguard.services.wireguard import WireGuardService


class Command(BaseCommand):
    help = 'Generate or regenerate WireGuard keys for a server'

    def add_arguments(self, parser):
        parser.add_argument(
            'server_id',
            type=int,
            help='ID of the WireGuard server'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate keys even if they already exist'
        )

    def handle(self, *args, **options):
        server_id = options['server_id']
        force = options.get('force', False)

        try:
            server = WireGuardServer.objects.get(id=server_id)
        except WireGuardServer.DoesNotExist:
            raise CommandError(f'WireGuard server with ID {server_id} does not exist')

        # Check if keys already exist
        has_private = server.private_key_encrypted and server.private_key_encrypted != "-" and len(server.private_key_encrypted) > 10
        has_public = server.public_key and server.public_key != "-"

        if has_private and has_public and not force:
            raise CommandError(
                f'Server "{server.name}" already has keys. Use --force to regenerate.'
            )

        self.stdout.write(f'Generating keys for server "{server.name}" ({server.endpoint})...')

        try:
            # Generate new keys
            private_key, public_key = WireGuardService.generate_keys()
            
            # Update server
            server.public_key = public_key
            server.set_private_key(private_key)
            server.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully generated keys for server "{server.name}"'
                )
            )
            self.stdout.write(f'Public key: {public_key[:30]}...')
            
        except Exception as e:
            raise CommandError(f'Failed to generate keys: {str(e)}')
