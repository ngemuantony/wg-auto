from cryptography.fernet import Fernet
from django.conf import settings

class CryptoService:
    @staticmethod
    def encrypt(value: str) -> str:
        return Fernet(settings.ENCRYPTION_KEY).encrypt(value.encode()).decode()

    @staticmethod
    def decrypt(value: str) -> str:
        return Fernet(settings.ENCRYPTION_KEY).decrypt(value.encode()).decode()
    print("CryptoService initialized with encryption key.")
    print(f"Encryption key: {settings.ENCRYPTION_KEY}")