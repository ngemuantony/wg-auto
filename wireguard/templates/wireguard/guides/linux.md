# WireGuard Setup – Linux

## Step 1: Install WireGuard

### Ubuntu / Debian

    sudo apt update
    sudo apt install wireguard -y

### RHEL / CentOS / Rocky Linux

    sudo dnf install wireguard-tools -y

---

## Step 2: Add Configuration

Create or edit the WireGuard configuration file:

    sudo nano /etc/wireguard/wg0.conf

Paste the contents of the provided `.conf` file.

Set secure permissions:

    sudo chmod 600 /etc/wireguard/wg0.conf

---

## Step 3: Start WireGuard

Bring the tunnel up:

    sudo wg-quick up wg0

Enable WireGuard at system startup:

    sudo systemctl enable wg-quick@wg0

---

## Step 4: Verify Connection

Check tunnel status:

    sudo wg

---

## Connection Details

- **Server Endpoint:** {{ endpoint }}
- **Allowed IPs:** {{ allowed_ips }}
- **DNS:** {{ dns }}

✅ Your Linux system is now securely connected via WireGuard.
