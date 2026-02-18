from cryptography.fernet import Fernet
from django.conf import settings
from typing import Union

class CryptoService:
    @staticmethod
    def encrypt(value: Union[str, bytes]) -> str:
        if isinstance(value, str):
            value = value.encode()
        return Fernet(settings.ENCRYPTION_KEY).encrypt(value).decode()

    @staticmethod
    def decrypt(value: str) -> str:
        return Fernet(settings.ENCRYPTION_KEY).decrypt(value.encode()).decode()
