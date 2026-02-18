from utils.crypto import CryptoService

def test_encrypt_decrypt():
    raw = "secret"
    enc = CryptoService.encrypt(raw)
    assert CryptoService.decrypt(enc) == raw
