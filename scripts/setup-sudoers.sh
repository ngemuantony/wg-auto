#!/usr/bin/env bash

########################################
# Setup WireGuard sudoers Configuration
########################################
# This script configures sudoers to allow a non-root user
# to run specific WireGuard commands without a password.
#
# Usage:
#   sudo bash scripts/setup-sudoers.sh <username>
#   Example: sudo bash scripts/setup-sudoers.sh www-data
#

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] This script must be run as root (use sudo)"
    exit 1
fi

if [ -z "$1" ]; then
    echo "[ERROR] Usage: $0 <username>"
    echo "Example: sudo bash $0 www-data"
    exit 1
fi

APP_USER="$1"
SUDOERS_FILE="/etc/sudoers.d/wireguard-auto-$APP_USER"

echo "[INFO] Configuring sudoers for user: $APP_USER"

# Verify user exists
if ! id "$APP_USER" &>/dev/null; then
    echo "[ERROR] User '$APP_USER' does not exist"
    exit 1
fi

# Create sudoers entry
cat > "$SUDOERS_FILE" <<'EOF'
# WireGuard Auto - Allow non-root user to run WireGuard commands without password
# This allows the Django application to:
# 1. Generate WireGuard keys (genkey, pubkey)
# 2. Inject/remove peers into live interface (set)
# 3. Query interface status (show)
# 4. Manage WireGuard interfaces (wg-quick)

Cmnd_Alias WG_COMMANDS = /usr/bin/wg, /usr/bin/wg-quick

EOF

# Append the user-specific entry
echo "$APP_USER ALL=(ALL) NOPASSWD: WG_COMMANDS" >> "$SUDOERS_FILE"

# Validate sudoers syntax
if ! visudo -c -f "$SUDOERS_FILE" &>/dev/null; then
    echo "[ERROR] Invalid sudoers syntax. Removing file."
    rm "$SUDOERS_FILE"
    exit 1
fi

# Set proper permissions
chmod 0440 "$SUDOERS_FILE"

echo "[SUCCESS] Sudoers configured at: $SUDOERS_FILE"
echo ""
echo "Configured permissions:"
echo "  User: $APP_USER"
echo "  Commands allowed (all /usr/bin/wg* commands):"
echo "    - wg genkey        (generate private keys)"
echo "    - wg pubkey        (derive public keys)"
echo "    - wg show          (query interface status)"
echo "    - wg set           (inject/remove peers live)"
echo "    - wg-quick up/down (manage interfaces)"
echo ""
echo "The user can now run these commands with: sudo wg <command>"
echo "without being prompted for a password."
echo ""
echo "[INFO] Testing sudoers configuration..."
if sudo -u "$APP_USER" -n sudo wg show &>/dev/null 2>&1; then
    echo "[SUCCESS] Configuration test passed! Commands should work."
else
    echo "[WARNING] Test indicated potential issues. Please verify manually."
fi
