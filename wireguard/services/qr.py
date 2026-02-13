# wireguard/services/qr.py
import os
import qrcode
from django.conf import settings
from django.utils import timezone


def get_qr_base_dir() -> str:
    return os.path.join(settings.BASE_DIR, "wireguard", "static", "qr")


def get_year_dir() -> str:
    year = timezone.now().year
    return os.path.join(get_qr_base_dir(), str(year))


def generate_qr(peer_id: str, config_text: str) -> str:
    """
    Generate a WireGuard QR code stored in a year-based directory.
    Returns the absolute path to the QR file.
    """
    year_dir = get_year_dir()
    os.makedirs(year_dir, exist_ok=True)

    filename = f"peer_{peer_id}.png"
    file_path = os.path.join(year_dir, filename)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )
    qr.add_data(config_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(file_path)

    return file_path
