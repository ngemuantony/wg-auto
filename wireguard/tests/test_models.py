from wireguard.models import WireGuardPeer

def test_private_key_encryption(db):
    peer = WireGuardPeer(name="A", email="a@a.com", public_key="pub", allowed_ip="10.0.0.2")
    peer.set_private_key("priv")
    assert peer.get_private_key() == "priv"
