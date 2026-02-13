#!/bin/bash
# WireGuard Auto - Systemd Service Management Helper
# This script provides convenience commands for managing the deployed application

set -e

SERVICES=("wireguard-auto" "wireguard-auto-celery" "wireguard-auto-celery-beat")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show services status
status() {
    info "Checking service status..."
    for service in "${SERVICES[@]}"; do
        if sudo systemctl is-active --quiet "$service"; then
            echo -e "${GREEN}✓${NC} $service: ${GREEN}running${NC}"
        else
            echo -e "${RED}✗${NC} $service: ${RED}stopped${NC}"
        fi
    done
}

# Start services
start() {
    info "Starting WireGuard Auto services..."
    for service in "${SERVICES[@]}"; do
        sudo systemctl start "$service"
        success "Started $service"
    done
}

# Stop services
stop() {
    info "Stopping WireGuard Auto services..."
    for service in "${SERVICES[@]}"; do
        sudo systemctl stop "$service"
        success "Stopped $service"
    done
}

# Restart all services
restart() {
    info "Restarting WireGuard Auto services..."
    for service in "${SERVICES[@]}"; do
        sudo systemctl restart "$service"
        success "Restarted $service"
    done
}

# Restart specific service
restart_service() {
    local service="$1"
    if [[ ! " ${SERVICES[@]} " =~ " ${service} " ]]; then
        error "Unknown service: $service"
        echo "Available services: ${SERVICES[*]}"
        return 1
    fi
    info "Restarting $service..."
    sudo systemctl restart "$service"
    success "Restarted $service"
}

# View logs
logs() {
    local service="${1:-wireguard-auto}"
    if [[ ! " ${SERVICES[@]} " =~ " ${service} " ]]; then
        error "Unknown service: $service"
        echo "Available services: ${SERVICES[*]}"
        return 1
    fi
    info "Showing logs for $service (last 50 lines)..."
    echo ""
    sudo journalctl -u "$service" -n 50 --no-pager
}

# Follow logs (tail -f style)
logs_follow() {
    local service="${1:-wireguard-auto}"
    if [[ ! " ${SERVICES[@]} " =~ " ${service} " ]]; then
        error "Unknown service: $service"
        echo "Available services: ${SERVICES[*]}"
        return 1
    fi
    info "Following logs for $service (press Ctrl+C to exit)..."
    echo ""
    sudo journalctl -u "$service" -f
}

# Reload services after updating code
reload() {
    info "Reloading WireGuard Auto..."
    success "Collecting static files..."
    cd /home/tisp/wg-auto
    source venv/bin/activate
    python manage.py collectstatic --noinput > /dev/null 2>&1 || true
    
    info "Restarting services..."
    restart
    success "Reload complete"
}

# Show help
show_help() {
    cat <<EOF
${BLUE}WireGuard Auto Service Manager${NC}

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    status [service]          Show status of services
    start                     Start all services
    stop                      Stop all services
    restart [service]         Restart services
    logs [service]            Show recent logs (default: wireguard-auto)
    logs-follow [service]     Follow logs in real-time (Ctrl+C to exit)
    reload                    Reload application (collect statics + restart)
    help                      Show this help message

Services:
    wireguard-auto            Main Django application
    wireguard-auto-celery     Celery worker for background tasks
    wireguard-auto-celery-beat Celery beat scheduler

Examples:
    $0 status
    $0 restart
    $0 restart wireguard-auto-celery
    $0 logs-follow wireguard-auto
    $0 reload

EOF
}

# Main
case "${1:-help}" in
    status)
        status
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        if [ -n "$2" ]; then
            restart_service "$2"
        else
            restart
        fi
        ;;
    logs)
        logs "$2"
        ;;
    logs-follow)
        logs_follow "$2"
        ;;
    reload)
        reload
        ;;
    help)
        show_help
        ;;
    *)
        error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
