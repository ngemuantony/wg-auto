#!/usr/bin/env bash
set -e

#====================================================================
# WireGuard Auto Installation Script
# Maintained by DEVELOPER ANTONY
#====================================================================

########################################
# CONSTANTS (DO NOT CHANGE)
########################################
SYSTEM_USER="wg-auto"
SYSTEM_GROUPS=("www-data" "wireguard")

BASE_DIR="/wg-auto"
INSTALL_DIR="${BASE_DIR}/wg-auto"

VENV_DIR="${INSTALL_DIR}/venv"
ENV_FILE="${INSTALL_DIR}/.env"
BACKUP_DIR="${INSTALL_DIR}/env_backups"
RUN_DIR="${INSTALL_DIR}/run"
LOG_DIR="${INSTALL_DIR}/logs"

DB_NAME="wireguard_db"
DB_USER="wireguard_user"
DB_HOST="localhost"
DB_PORT="5432"

REDIS_HOST="127.0.0.1"
REDIS_PORT="6379"

ALLOWED_HOSTS="localhost,127.0.0.1"
CURRENT_DIR="$(pwd)"

SOURCE_USER=""
SOURCE_GROUP=""

########################################
# LOGGING
########################################
log_info()    { echo -e "\e[34m[INFO]\e[0m $1"; }
log_success() { echo -e "\e[32m[SUCCESS]\e[0m $1"; }
log_warning() { echo -e "\e[33m[WARNING]\e[0m $1"; }
log_error()   { echo -e "\e[31m[ERROR]\e[0m $1"; }

prompt_yes_no() {
    while true; do
        read -rp "$1 (yes/no): " yn
        case "$yn" in
            [Yy]* ) return 0 ;;
            [Nn]* ) return 1 ;;
            * ) echo "Please answer yes or no." ;;
        esac
    done
}

########################################
# ROOT CHECK
########################################
if [[ "$EUID" -ne 0 ]]; then
    log_error "Run with sudo: sudo bash install.sh"
    exit 1
fi

########################################
# SYSTEM USER + PERMISSIONS
########################################
setup_system_user() {
    log_info "Ensuring system user ${SYSTEM_USER}"

    id "$SYSTEM_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$SYSTEM_USER"

    for grp in "${SYSTEM_GROUPS[@]}"; do
        getent group "$grp" &>/dev/null || groupadd "$grp"
        usermod -aG "$grp" "$SYSTEM_USER"
    done

    [[ -n "$SOURCE_GROUP" && "$SOURCE_GROUP" != "$SYSTEM_USER" ]] && {
        getent group "$SOURCE_GROUP" &>/dev/null || groupadd "$SOURCE_GROUP"
        usermod -aG "$SOURCE_GROUP" "$SYSTEM_USER"
    }

    [[ -n "$SOURCE_USER" && "$SOURCE_USER" != "root" ]] && usermod -aG "$SYSTEM_USER" "$SOURCE_USER"
    usermod -aG "$SYSTEM_USER" www-data

    bash "$INSTALL_DIR/scripts/setup-sudoers.sh" "$SYSTEM_USER"
    log_success "System user and sudoers configured"
}

########################################
# SYSTEM PACKAGES
########################################
install_system_packages() {
    apt update
    apt install -y \
        python3 python3-venv python3-pip \
        postgresql postgresql-contrib \
        redis-server wireguard nginx rsync curl git
}

########################################
# POSTGRESQL
########################################
setup_postgres() {
    generate_password() {
        python3 - <<EOF
import secrets; print(secrets.token_urlsafe(24))
EOF
    }

    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
        prompt_yes_no "Reset DB password?" && {
            DB_PASSWORD="$(generate_password)"
            sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
        } || read -rsp "Enter existing DB password: " DB_PASSWORD && echo
    else
        DB_PASSWORD="$(generate_password)"
        sudo -u postgres psql <<EOF
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
EOF
    fi
}

########################################
# REDIS
########################################
setup_redis() {
    systemctl enable redis-server --now
    redis-cli ping >/dev/null
}

########################################
# PROJECT DEPLOYMENT
########################################
setup_project() {
    read -rp "Source project path [${CURRENT_DIR}]: " PROJECT_PATH
    PROJECT_PATH="${PROJECT_PATH:-$CURRENT_DIR}"

    [[ -f "${PROJECT_PATH}/manage.py" ]] || { log_error "manage.py not found"; exit 1; }

    SOURCE_USER="$(stat -c '%U' "$PROJECT_PATH")"
    SOURCE_GROUP="$(stat -c '%G' "$PROJECT_PATH")"

    mkdir -p "$INSTALL_DIR"
    rsync -a --delete --exclude venv --exclude __pycache__ "${PROJECT_PATH}/" "${INSTALL_DIR}/"

    mkdir -p "$RUN_DIR" "$LOG_DIR" "$BACKUP_DIR" "${INSTALL_DIR}/.run"

    chown -R "$SYSTEM_USER:$SYSTEM_USER" "$BASE_DIR"
    chown -R "$SYSTEM_USER":www-data "${INSTALL_DIR}/.run"
    chmod 2770 "$RUN_DIR" "$LOG_DIR" "$BACKUP_DIR" "${INSTALL_DIR}/.run"
}

########################################
# VIRTUALENV
########################################
setup_venv() {
    [[ -x "${VENV_DIR}/bin/python" ]] || {
        sudo -u "$SYSTEM_USER" python3 -m venv "$VENV_DIR"
        sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/pip" install --upgrade pip
        sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    }
}

########################################
# ENV FILE + ENCRYPTION KEY (CRITICAL)
########################################
setup_env() {
    mkdir -p "$BACKUP_DIR"
    [[ -f "$ENV_FILE" ]] && cp "$ENV_FILE" "$BACKUP_DIR/.env.$(date +%s)"

    SECRET_KEY="$(python3 - <<EOF
import secrets; print(secrets.token_urlsafe(50))
EOF
)"

    cat > "$ENV_FILE" <<EOF
DEBUG=0
DJANGO_SECRET_KEY=${SECRET_KEY}

DATABASE_NAME=${DB_NAME}
DATABASE_USER=${DB_USER}
DATABASE_PASSWORD=${DB_PASSWORD}
DATABASE_HOST=${DB_HOST}
DATABASE_PORT=${DB_PORT}

REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}

CELERY_BROKER_URL=redis://${REDIS_HOST}:${REDIS_PORT}/0
CELERY_RESULT_BACKEND=redis://${REDIS_HOST}:${REDIS_PORT}/0

ALLOWED_HOSTS=${ALLOWED_HOSTS}
EOF

    read -rp "Enter existing ENCRYPTION_KEY or press ENTER to generate new: " USER_KEY

    if [[ -n "$USER_KEY" ]]; then
        ENCRYPTION_KEY="$USER_KEY"
    else
        ENCRYPTION_KEY="$(python3 - <<EOF
import secrets, base64
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
EOF
)"
    fi

    python3 - <<EOF || { log_error "Invalid ENCRYPTION_KEY"; exit 1; }
import base64, sys
key="${ENCRYPTION_KEY}"
assert len(key) == 44
base64.urlsafe_b64decode(key)
EOF

    echo "ENCRYPTION_KEY=${ENCRYPTION_KEY}" >> "$ENV_FILE"

    LAST_ENV="$(ls -1 "$BACKUP_DIR"/.env.* 2>/dev/null | tail -n 1 || true)"
    if [[ -n "$LAST_ENV" ]]; then
        OLD_KEY="$(grep '^ENCRYPTION_KEY=' "$LAST_ENV" | cut -d= -f2 || true)"
        if [[ -n "$OLD_KEY" && "$OLD_KEY" != "$ENCRYPTION_KEY" ]]; then
            prompt_yes_no "Reset encrypted WireGuard keys?" || exit 1
            sudo -u "$SYSTEM_USER" bash <<EOF
cd "$INSTALL_DIR"
set -a; source .env; set +a
${VENV_DIR}/bin/python manage.py shell <<PY
from wireguard.models import WireGuardServer, WireGuardPeer
WireGuardServer.objects.update(private_key_encrypted=None)
WireGuardPeer.objects.update(private_key_encrypted=None)
print("Encrypted keys cleared")
PY
EOF
        fi
    fi

    chown "$SYSTEM_USER:$SYSTEM_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

########################################
# DJANGO
########################################
setup_django() {
    sudo -u "$SYSTEM_USER" bash <<EOF
cd "$INSTALL_DIR"
set -a; source .env; set +a
${VENV_DIR}/bin/python manage.py makemigrations
${VENV_DIR}/bin/python manage.py migrate
${VENV_DIR}/bin/python manage.py collectstatic --noinput
EOF
}

########################################
# SUPERVISOR
########################################
setup_supervisor() {
    rm -f "${INSTALL_DIR}/.run/"*.pid "${INSTALL_DIR}/.run/supervisor.sock"

    SYSTEMD_FILE="/etc/systemd/system/wg-auto-supervisor.service"
    cat > "$SYSTEMD_FILE" <<EOF
[Unit]
Description=WireGuard Auto Supervisor
After=network.target redis-server.service postgresql.service

[Service]
Type=forking
User=${SYSTEM_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/supervisord -c ${INSTALL_DIR}/wg-auto-supervisor.conf
ExecStop=${VENV_DIR}/bin/supervisorctl shutdown
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable wg-auto-supervisor
    systemctl restart wg-auto-supervisor
}

########################################
# NGINX
########################################
setup_nginx() {
    cp "${INSTALL_DIR}/scripts/wg-auto.conf" /etc/nginx/sites-available/wg-auto.conf
    ln -sf /etc/nginx/sites-available/wg-auto.conf /etc/nginx/sites-enabled/wg-auto.conf
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl restart nginx
}

########################################
# MAIN
########################################
main() {
    prompt_yes_no "Proceed with installation?" || exit 0
    setup_project
    setup_system_user
    install_system_packages
    setup_postgres
    setup_redis
    setup_venv
    setup_env
    setup_django
    setup_supervisor
    setup_nginx
    log_success "Installation completed successfully"
}

main
