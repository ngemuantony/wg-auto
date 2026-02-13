from django.apps import AppConfig


class WireguardConfig(AppConfig):
    name = 'wireguard'

    def ready(self):
        import wireguard.signals