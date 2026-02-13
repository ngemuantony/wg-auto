#!/usr/bin/env bash
set -e

########################################
# CONFIG
########################################
INSTALL_DIR="/opt/wireguard-auto"
VENV_DIR="$INSTALL_DIR/venv"
ENV_FILE="$INSTALL_DIR/.env"
BACKUP_DIR="$INSTALL_DIR/env_backups"

DB_NAME="wireguard_db"
DB_USER="wireguard_user"
DB_HOST="localhost"
DB_PORT="5432"

REDIS_HOST="127.0.0.1"
REDIS_PORT="6379"

ALLOWED_HOSTS="localhost,127.0.0.1"

########################################
# LOGGING
########################################
log_info() {
    echo -e "\e[34m[INFO]\e[0m $1"
}

log_success() {
    echo -e "\e[32m[SUCCESS]\e[0m $1"
}

log_warning() {
    echo -e "\e[33m[WARNING]\e[0m $1"
}

log_error() {
    echo -e "\e[31m[ERROR]\e[0m $1"
}

prompt_yes_no() {
    local prompt_msg="$1"
    local response
    while true; do
        read -p "$prompt_msg (yes/no): " response
        case "$response" in
            [Yy][Ee][Ss]|[Yy])
                return 0
                ;;
            [Nn][Oo]|[Nn])
                return 1
                ;;
            *)
                echo "Please answer yes or no."
                ;;
        esac
    done
}

prompt_input() {
    local prompt_msg="$1"
    local default_value="$2"
    local response
    
    if [ -n "$default_value" ]; then
        read -p "$prompt_msg [$default_value]: " response
        echo "${response:-$default_value}"
    else
        read -p "$prompt_msg: " response
        echo "$response"
    fi
}

########################################
# ROOT CHECK
########################################
if [ "$EUID" -ne 0 ]; then
    log_error "Please run this script as root"
    exit 1
fi

########################################
# SYSTEM PACKAGES
########################################
install_system_packages() {
    log_info "Installing system packages..."
    log_info "Required packages: python3, postgresql, redis-server, wireguard, git, curl"
    
    if ! prompt_yes_no "Continue with system package installation?"; then
        log_warning "Package installation skipped"
        return 0
    fi

    apt update
    apt install -y \
        python3 \
        python3-venv \
        python3-pip \
        postgresql \
        postgresql-contrib \
        redis-server \
        wireguard \
        curl \
        git

    log_success "System packages installed"
}

########################################
# POSTGRESQL SETUP
########################################
setup_postgres() {
    log_info "Configuring PostgreSQL..."

    systemctl enable postgresql >/dev/null 2>&1 || true
    systemctl start postgresql

    # Always generate a new secure password
    NEW_DB_PASSWORD=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)

    # Check if user exists
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        log_info "Creating PostgreSQL user and database..."
        sudo -u postgres psql <<EOF
CREATE USER $DB_USER WITH PASSWORD '$NEW_DB_PASSWORD';
CREATE DATABASE $DB_NAME OWNER $DB_USER;
EOF
        log_success "PostgreSQL user and database created"
        DB_PASSWORD="$NEW_DB_PASSWORD"
    else
        log_info "PostgreSQL user '$DB_USER' already exists"
        
        if prompt_yes_no "Would you like to set a new password for this user?"; then
            sudo -u postgres psql <<EOF
ALTER USER $DB_USER WITH PASSWORD '$NEW_DB_PASSWORD';
EOF
            log_success "Password updated"
            DB_PASSWORD="$NEW_DB_PASSWORD"
        else
            if prompt_yes_no "Would you like to provide the existing password?"; then
                read -sp "Enter the password for $DB_USER: " DB_PASSWORD
                echo ""
                # Verify the password works
                if PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -h "$DB_HOST" -d "postgres" -c "SELECT 1" > /dev/null 2>&1; then
                    log_success "Password verified"
                else
                    log_error "Password verification failed"
                    exit 1
                fi
            else
                log_error "Cannot proceed without database password. Please run the script again and choose to reset the password."
                exit 1
            fi
        fi
    fi
}

########################################
# REDIS SETUP
########################################
setup_redis() {
    log_info "Configuring Redis..."

    systemctl enable redis-server >/dev/null 2>&1 || true
    systemctl start redis-server

    # Give Redis a moment to start
    sleep 1

    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
        log_success "Redis is running and accessible"
    else
        log_error "Redis failed to respond or is not running"
        if prompt_yes_no "Would you like to try restarting Redis?"; then
            systemctl restart redis-server
            sleep 2
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
                log_success "Redis restarted successfully"
            else
                log_error "Redis is still not responding"
                exit 1
            fi
        else
            exit 1
        fi
    fi
}

########################################
# PROJECT SETUP
########################################
setup_project() {
    log_info "Setting up project directory..."

    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$INSTALL_DIR/run"
    mkdir -p "$INSTALL_DIR/logs"
    cd "$INSTALL_DIR"

    # Check if project files exist
    if [ ! -f "manage.py" ]; then
        log_warning "Project files not found in $INSTALL_DIR"
        
        if prompt_yes_no "Would you like to copy project files from current directory?"; then
            if [ -f "$(pwd -P)/../manage.py" ] || [ -f "./manage.py" ]; then
                log_info "Copying project files..."
                # This assumes the script is run from the project root or scripts directory
                if [ -f "../manage.py" ]; then
                    cp -r ../* "$INSTALL_DIR/" 2>/dev/null || true
                    log_success "Project files copied"
                fi
            else
                log_error "Could not find manage.py to copy"
                exit 1
            fi
        else
            log_error "Project files are required. Please ensure manage.py exists in $INSTALL_DIR"
            exit 1
        fi
    fi

    # Check if pip executable exists, not just the directory
    if [ ! -f "$VENV_DIR/bin/pip" ]; then
        log_info "Creating virtual environment..."
        # Remove incomplete venv if it exists
        if [ -d "$VENV_DIR" ]; then
            log_info "Cleaning up incomplete virtual environment..."
            rm -rf "$VENV_DIR"
        fi
        
        if python3 -m venv "$VENV_DIR"; then
            log_success "Virtual environment created"
        else
            log_error "Failed to create virtual environment"
            exit 1
        fi
    else
        log_info "Virtual environment already exists"
    fi

    log_info "Upgrading pip..."
    if ! "$VENV_DIR/bin/pip" install --upgrade pip; then
        log_error "Failed to upgrade pip"
        exit 1
    fi

    if [ -f "requirements.txt" ]; then
        log_info "Installing Python dependencies..."
        if "$VENV_DIR/bin/pip" install -r requirements.txt; then
            log_success "Python dependencies installed"
        else
            log_error "Failed to install Python dependencies"
            exit 1
        fi
    else
        log_warning "requirements.txt not found"
    fi

    # Ensure Django is installed
    if ! "$VENV_DIR/bin/python" -c "import django" 2>/dev/null; then
        log_warning "Django not found, installing Django..."
        "$VENV_DIR/bin/pip" install "django>=4.2,<6.0"
        log_success "Django installed"
    else
        log_info "Django is already installed"
    fi
}

########################################
# ENV FILE
########################################
setup_env() {
    log_info "Configuring environment variables..."

    # If .env exists and password was changed, we MUST update it
    if [ -f "$ENV_FILE" ] && [ -n "$DB_PASSWORD" ]; then
        log_warning "PostgreSQL password was changed - .env file must be updated"
        
        if prompt_yes_no "Would you like to back up and update the .env file?"; then
            cp "$ENV_FILE" "$BACKUP_DIR/.env.$(date +%F-%H%M%S)"
            log_info "Existing .env backed up"
            
            # Extract existing values from .env, with proper defaults
            # Try DATABASE_* first, then fall back to POSTGRES_* for backwards compatibility
            DB_NAME=$(grep "^DATABASE_NAME=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_NAME=""
            [ -z "$DB_NAME" ] && DB_NAME=$(grep "^POSTGRES_DB=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_NAME=""
            [ -z "$DB_NAME" ] && DB_NAME="wireguard_db"
            
            DB_USER=$(grep "^DATABASE_USER=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_USER=""
            [ -z "$DB_USER" ] && DB_USER=$(grep "^POSTGRES_USER=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_USER=""
            [ -z "$DB_USER" ] && DB_USER="wireguard_user"
            
            DB_HOST=$(grep "^DATABASE_HOST=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_HOST=""
            [ -z "$DB_HOST" ] && DB_HOST=$(grep "^POSTGRES_HOST=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_HOST=""
            [ -z "$DB_HOST" ] && DB_HOST="localhost"
            
            DB_PORT=$(grep "^DATABASE_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_PORT=""
            [ -z "$DB_PORT" ] && DB_PORT=$(grep "^POSTGRES_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DB_PORT=""
            [ -z "$DB_PORT" ] && DB_PORT="5432"
            
            REDIS_HOST=$(grep "^REDIS_HOST=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || REDIS_HOST=""
            [ -z "$REDIS_HOST" ] && REDIS_HOST="127.0.0.1"
            
            REDIS_PORT=$(grep "^REDIS_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || REDIS_PORT=""
            [ -z "$REDIS_PORT" ] && REDIS_PORT="6379"
            
            ALLOWED_HOSTS=$(grep "^ALLOWED_HOSTS=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || ALLOWED_HOSTS=""
            [ -z "$ALLOWED_HOSTS" ] && ALLOWED_HOSTS="localhost,127.0.0.1"
            
            DJANGO_SECRET=$(grep "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DJANGO_SECRET=""
            [ -z "$DJANGO_SECRET" ] && DJANGO_SECRET=$(grep "^DJANGO_SECRET_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || DJANGO_SECRET=""
            
            # Filter out placeholder values like "changeme" or "dev-secret-key"
            if [ "$DJANGO_SECRET" = "changeme" ] || [ "$DJANGO_SECRET" = "dev-secret-key" ] || [ "$DJANGO_SECRET" = "devkey1234567890" ]; then
                DJANGO_SECRET=""
            fi
            
            log_info "Extracted values from existing .env:"
            log_info "  Database: $DB_NAME, User: $DB_USER, Host: $DB_HOST, Port: $DB_PORT"
            
            # Generate SECRET_KEY if it doesn't exist or is a placeholder
            if [ -z "$DJANGO_SECRET" ]; then
                DJANGO_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
                if [ -z "$DJANGO_SECRET" ]; then
                    log_error "Failed to generate SECRET_KEY"
                    exit 1
                fi
                log_info "Generated new SECRET_KEY"
            fi
            
            # Generate ENCRYPTION_KEY if it doesn't exist
            ENCRYPTION_KEY=$(grep "^ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-) || ENCRYPTION_KEY=""
            if [ -z "$ENCRYPTION_KEY" ]; then
                ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
                if [ -z "$ENCRYPTION_KEY" ]; then
                    log_error "Failed to generate ENCRYPTION_KEY"
                    exit 1
                fi
                log_info "Generated new ENCRYPTION_KEY"
            fi
            
            # Write the updated .env file with proper escaping
            cat > "$ENV_FILE" <<'EOF_ENV'
DEBUG=0
EOF_ENV
            
            echo "SECRET_KEY=$DJANGO_SECRET" >> "$ENV_FILE"
            echo "DJANGO_SECRET_KEY=$DJANGO_SECRET" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "# Encryption key for storing sensitive data (WireGuard private keys, SMTP passwords)" >> "$ENV_FILE"
            echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "DATABASE_NAME=$DB_NAME" >> "$ENV_FILE"
            echo "DATABASE_USER=$DB_USER" >> "$ENV_FILE"
            echo "DATABASE_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
            echo "DATABASE_HOST=$DB_HOST" >> "$ENV_FILE"
            echo "DATABASE_PORT=$DB_PORT" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "# Legacy POSTGRES_ variables (for compatibility)" >> "$ENV_FILE"
            echo "POSTGRES_DB=$DB_NAME" >> "$ENV_FILE"
            echo "POSTGRES_USER=$DB_USER" >> "$ENV_FILE"
            echo "POSTGRES_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
            echo "POSTGRES_HOST=$DB_HOST" >> "$ENV_FILE"
            echo "POSTGRES_PORT=$DB_PORT" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "REDIS_HOST=$REDIS_HOST" >> "$ENV_FILE"
            echo "REDIS_PORT=$REDIS_PORT" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "CELERY_BROKER_URL=redis://$REDIS_HOST:$REDIS_PORT/0" >> "$ENV_FILE"
            echo "CELERY_RESULT_BACKEND=redis://$REDIS_HOST:$REDIS_PORT/0" >> "$ENV_FILE"
            echo "" >> "$ENV_FILE"
            echo "ALLOWED_HOSTS=$ALLOWED_HOSTS" >> "$ENV_FILE"
            
            chmod 600 "$ENV_FILE"
            log_success ".env file updated with new database password"
            
            # Verify the .env file was updated with all critical values
            if grep -q "DATABASE_USER=$DB_USER" "$ENV_FILE"; then
                log_info "Verification: DATABASE_USER is set to $DB_USER"
            else
                log_error "Verification failed: DATABASE_USER not found in .env"
                exit 1
            fi
            
            if grep -q "^SECRET_KEY=" "$ENV_FILE"; then
                log_info "Verification: SECRET_KEY is set"
            else
                log_error "Verification failed: SECRET_KEY not found in .env"
                exit 1
            fi
            
            return 0
        else
            log_error "Cannot proceed without updating .env with the new password"
            exit 1
        fi
    fi

    if [ -f "$ENV_FILE" ]; then
        if prompt_yes_no "Would you like to reconfigure the entire .env file?"; then
            cp "$ENV_FILE" "$BACKUP_DIR/.env.$(date +%F-%H%M%S)"
            log_info "Existing .env backed up"
        else
            log_info "Keeping existing .env file"
            return 0
        fi
    fi

    # Prompt for custom values
    echo ""
    log_info "Database Configuration"
    DB_NAME=$(prompt_input "Database name" "$DB_NAME")
    DB_USER=$(prompt_input "Database user" "$DB_USER")
    DB_HOST=$(prompt_input "Database host" "$DB_HOST")
    DB_PORT=$(prompt_input "Database port" "$DB_PORT")
    
    echo ""
    log_info "Redis Configuration"
    REDIS_HOST=$(prompt_input "Redis host" "$REDIS_HOST")
    REDIS_PORT=$(prompt_input "Redis port" "$REDIS_PORT")
    
    echo ""
    log_info "Django Configuration"
    ALLOWED_HOSTS=$(prompt_input "Allowed hosts" "$ALLOWED_HOSTS")
    
    # Generate SECRET_KEY
    DJANGO_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    if [ -z "$DJANGO_SECRET" ]; then
        log_error "Failed to generate SECRET_KEY"
        exit 1
    fi
    
    # Generate ENCRYPTION_KEY
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    if [ -z "$ENCRYPTION_KEY" ]; then
        log_error "Failed to generate ENCRYPTION_KEY"
        exit 1
    fi

    echo ""
    log_info "Generated SECRET_KEY and ENCRYPTION_KEY (will be saved to .env)"
    echo ""

    # Write .env file using echo commands to avoid variable substitution issues
    cat > "$ENV_FILE" <<'EOF_ENV'
DEBUG=0
EOF_ENV
    
    echo "SECRET_KEY=$DJANGO_SECRET" >> "$ENV_FILE"
    echo "DJANGO_SECRET_KEY=$DJANGO_SECRET" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "# Encryption key for storing sensitive data (WireGuard private keys, SMTP passwords)" >> "$ENV_FILE"
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "DATABASE_NAME=$DB_NAME" >> "$ENV_FILE"
    echo "DATABASE_USER=$DB_USER" >> "$ENV_FILE"
    echo "DATABASE_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
    echo "DATABASE_HOST=$DB_HOST" >> "$ENV_FILE"
    echo "DATABASE_PORT=$DB_PORT" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "# Legacy POSTGRES_ variables (for compatibility)" >> "$ENV_FILE"
    echo "POSTGRES_DB=$DB_NAME" >> "$ENV_FILE"
    echo "POSTGRES_USER=$DB_USER" >> "$ENV_FILE"
    echo "POSTGRES_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
    echo "POSTGRES_HOST=$DB_HOST" >> "$ENV_FILE"
    echo "POSTGRES_PORT=$DB_PORT" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "REDIS_HOST=$REDIS_HOST" >> "$ENV_FILE"
    echo "REDIS_PORT=$REDIS_PORT" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "CELERY_BROKER_URL=redis://$REDIS_HOST:$REDIS_PORT/0" >> "$ENV_FILE"
    echo "CELERY_RESULT_BACKEND=redis://$REDIS_HOST:$REDIS_PORT/0" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "ALLOWED_HOSTS=$ALLOWED_HOSTS" >> "$ENV_FILE"

    chmod 600 "$ENV_FILE"
    
    # Verify the .env file was created properly
    if grep -q "^SECRET_KEY=" "$ENV_FILE" && grep -q "^DATABASE_USER=" "$ENV_FILE"; then
        log_success ".env file created/updated"
    else
        log_error "Failed to create proper .env file"
        exit 1
    fi
}

########################################
# DJANGO SETUP
########################################
setup_django() {
    log_info "Running Django setup..."

    cd "$INSTALL_DIR"

    # Load environment variables
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found at $ENV_FILE"
        exit 1
    fi

    # Export all variables from .env
    set -a
    source "$ENV_FILE"
    set +a

    # Verify environment variables are set
    log_info "Verifying database configuration..."
    if [ -z "$DATABASE_USER" ]; then
        log_error "DATABASE_USER not set in environment"
        exit 1
    fi
    log_info "Using database user: $DATABASE_USER"
    
    # Verify SECRET_KEY is set and not a placeholder
    if [ -z "$SECRET_KEY" ] && [ -z "$DJANGO_SECRET_KEY" ]; then
        log_error "SECRET_KEY not set in environment"
        exit 1
    fi
    
    if [ "$SECRET_KEY" = "changeme" ] || [ "$DJANGO_SECRET_KEY" = "changeme" ]; then
        log_warning "WARNING: Using placeholder SECRET_KEY 'changeme'. This is a security issue."
    fi
    
    log_info "SECRET_KEY is properly configured"

    log_info "Running migrations..."
    if DB_USER="$DATABASE_USER" "$VENV_DIR/bin/python" manage.py migrate; then
        log_success "Migrations completed"
    else
        log_error "Migration failed"
        exit 1
    fi

    log_info "Collecting static files..."
    if PYTHONPATH="$INSTALL_DIR" "$VENV_DIR/bin/python" manage.py collectstatic --noinput 2>/dev/null; then
        log_success "Static files collected"
    else
        log_warning "Static files collection had warnings (this is usually OK)"
    fi

    log_success "Django setup completed"
}

########################################
# INSTALLATION SUMMARY
########################################
show_summary() {
    echo ""
    echo "=========================================="
    echo "WireGuard Auto Installation Summary"
    echo "=========================================="
    echo "Installation Directory: $INSTALL_DIR"
    echo "Virtual Environment: $VENV_DIR"
    echo "Environment File: $ENV_FILE"
    echo ""
    echo "Database:"
    echo "  Name: $DB_NAME"
    echo "  User: $DB_USER"
    echo "  Host: $DB_HOST"
    echo "  Port: $DB_PORT"
    echo ""
    echo "Redis:"
    echo "  Host: $REDIS_HOST"
    echo "  Port: $REDIS_PORT"
    echo ""
    echo "Allowed Hosts: $ALLOWED_HOSTS"
    echo "=========================================="
    echo ""
}

########################################
# MAIN
########################################
main() {
    echo ""
    echo "=========================================="
    echo "WireGuard Auto Installation Script"
    echo "=========================================="
    echo ""
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run this script as root (use: sudo bash scripts/install.sh)"
        exit 1
    fi
    
    # Prompt for installation directory
    INSTALL_DIR=$(prompt_input "Installation directory" "$INSTALL_DIR")
    VENV_DIR="$INSTALL_DIR/venv"
    ENV_FILE="$INSTALL_DIR/.env"
    BACKUP_DIR="$INSTALL_DIR/env_backups"
    
    echo ""
    if ! prompt_yes_no "Proceed with installation to $INSTALL_DIR?"; then
        log_warning "Installation cancelled"
        exit 0
    fi
    
    # Run installation steps
    install_system_packages
    setup_postgres
    setup_redis
    setup_project
    
    # Show summary before env setup
    show_summary
    
    if prompt_yes_no "Proceed with environment configuration?"; then
        setup_env
        setup_django
        
        # Configure sudoers for WireGuard key generation
        log_info "Configuring sudo access for WireGuard commands..."
        
        # Try to determine the app user (www-data for nginx, or current user for dev)
        APP_USER="${SUDO_USER:-www-data}"
        
        if prompt_yes_no "Configure sudoers for user '$APP_USER' to run WireGuard commands without password?"; then
            if [ -f "$INSTALL_DIR/scripts/setup-sudoers.sh" ]; then
                sudo bash "$INSTALL_DIR/scripts/setup-sudoers.sh" "$APP_USER"
                if [ $? -eq 0 ]; then
                    log_success "Sudoers configured successfully"
                else
                    log_warning "Sudoers configuration had issues. Manual setup may be needed."
                fi
            else
                log_warning "setup-sudoers.sh not found. Skipping sudoers configuration."
                log_info "You can manually configure it later by running:"
                log_info "  sudo bash $INSTALL_DIR/scripts/setup-sudoers.sh <username>"
            fi
        else
            log_info "Sudoers configuration skipped. You can set it up manually later."
        fi
        
        echo ""
        log_success "WireGuard Auto setup completed successfully 🚀"
        echo ""
        log_info "Next steps for production deployment:"
        echo ""
        echo "1. Ensure sudoers is configured for WireGuard key generation:"
        echo "   sudo bash $INSTALL_DIR/scripts/setup-sudoers.sh www-data"
        echo ""
        echo "2. Install Gunicorn and configure systemd services:"
        echo "   sudo cp $INSTALL_DIR/docker/wireguard-auto.service /etc/systemd/system/"
        echo "   sudo cp $INSTALL_DIR/docker/wireguard-auto-celery.service /etc/systemd/system/"
        echo "   sudo cp $INSTALL_DIR/docker/wireguard-auto-celery-beat.service /etc/systemd/system/"
        echo ""
        echo "3. Configure nginx reverse proxy:"
        echo "   sudo cp $INSTALL_DIR/docker/nginx.conf /etc/nginx/sites-available/wireguard-auto"
        echo "   sudo ln -s /etc/nginx/sites-available/wireguard-auto /etc/nginx/sites-enabled/"
        echo "   sudo nginx -t && sudo systemctl restart nginx"
        echo ""
        echo "4. Enable and start services:"
        echo "   sudo systemctl daemon-reload"
        echo "   sudo systemctl enable wireguard-auto wireguard-auto-celery wireguard-auto-celery-beat"
        echo "   sudo systemctl start wireguard-auto wireguard-auto-celery wireguard-auto-celery-beat"
        echo ""
        echo "5. Monitor services:"
        echo "   sudo journalctl -u wireguard-auto -f"
        echo "   sudo journalctl -u wireguard-auto-celery -f"
        echo ""
        echo "For development testing (without systemd):"
        echo "   cd $INSTALL_DIR && source venv/bin/activate"
        echo "   python manage.py runserver"
    else
        log_warning "Environment configuration skipped"
        log_info "You can configure it manually by running: source $VENV_DIR/bin/activate && cd $INSTALL_DIR && python manage.py migrate"
    fi
}

main

#-------------------------------------------------------------------------------------------------------------------------------------
#CREATED AND MANTAINED BY:      DEVELOPER ANTONY
#                               developerantony98@gmail.com
#                  GitHub:      ngemuantony
#                  YouTube:     tispadmin
#                  Linkedin:    ngemuantony
#                  TikTok:      tispadmin                   

#-------------------------------------------------------------------------------------------------------------------------------------