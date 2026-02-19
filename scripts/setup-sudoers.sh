#!/usr/bin/env bash

########################################
# Setup WireGuard sudoers Configuration
########################################
# This script configures sudoers to allow non-root users
# to run specific WireGuard commands without a password.
#
# Usage:
#   sudo bash scripts/setup-sudoers.sh <username>
#   Example: sudo bash scripts/setup-sudoers.sh wg-auto
#

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] This script must be run as root (use sudo)"
    exit 1
fi

if [ -z "$1" ]; then
    echo "[ERROR] Usage: $0 <username>"
    echo "Example: sudo bash $0 wg-auto"
    exit 1
fi

APP_USER="$1"
SUDOERS_FILE="/etc/sudoers.d/wireguard-auto"

echo "[INFO] Configuring sudoers for user: $APP_USER"

# Verify user exists
if ! id "$APP_USER" &>/dev/null; then
    echo "[ERROR] User '$APP_USER' does not exist"
    exit 1
fi

# Create or update the sudoers file
cat > "$SUDOERS_FILE" <<EOF
# WireGuard Auto - Allow non-root users to run WireGuard commands without password
# This allows the application to:
# - Generate keys
# - Inject/remove peers
# - Query interface status
# - Manage WireGuard interfaces
Cmnd_Alias WG_COMMANDS = \
    /usr/bin/wg, \
    /usr/bin/wg-quick, \
    /usr/bin/tee, \
    /usr/bin/chmod

$APP_USER ALL=(root) NOPASSWD: WG_COMMANDS
EOF

# Set proper permissions
chmod 0440 "$SUDOERS_FILE"

# Validate sudoers syntax
if ! visudo -c -f "$SUDOERS_FILE" &>/dev/null; then
    echo "[ERROR] Invalid sudoers syntax. Please check $SUDOERS_FILE manually."
    exit 1
fi

echo "[SUCCESS] Sudoers configuration completed at: $SUDOERS_FILE"
echo ""
echo "Configured permissions:"
echo "  User: $APP_USER"
echo "  Commands allowed:"
echo "    - wg genkey        (generate private keys)"
echo "    - wg pubkey        (derive public keys)"
echo "    - wg show          (query interface status)"
echo "    - wg set           (inject/remove peers live)"
echo "    - wg-quick up/down (manage interfaces)"
echo "    - tee              (write configs to /etc/wireguard)"
echo "    - chmod            (set proper permissions on configs)"
echo ""

echo "[INFO] Testing sudoers configuration..."
if sudo -u "$APP_USER" -n sudo wg show &>/dev/null 2>&1; then
    echo "[SUCCESS] Configuration test passed! Commands should work without password."
else
    echo "[WARNING] Test indicated potential issues. Please verify manually."
fi
