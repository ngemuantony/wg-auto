import pytest
from wireguard_app.services.guides import InstallationGuideService, GuideContext


@pytest.mark.django_db
def test_windows_guide_generation():
    guide = InstallationGuideService.generate(
        GuideContext(
            peer_name="test",
            server_endpoint="vpn.example.com:51820",
            allowed_ips="0.0.0.0/0",
            dns="1.1.1.1",
            platform="windows",
        )
    )

    assert "WireGuard Setup – Windows" in guide
