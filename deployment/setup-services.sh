#!/bin/bash
# Setup script for i-TAT Bot systemd services
# This script installs and configures systemd services for:
# - FastAPI application (main.py)
# - Celery worker
# - Celery beat scheduler

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="i-tat-bot"
SERVICE_USER="www-data"
SERVICE_GROUP="www-data"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

print_info "Starting i-TAT Bot services setup..."

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_warning "Project directory $PROJECT_DIR does not exist"
    read -p "Enter the actual project directory path: " PROJECT_DIR
    
    if [ ! -d "$PROJECT_DIR" ]; then
        print_error "Directory $PROJECT_DIR does not exist"
        exit 1
    fi
fi

print_info "Using project directory: $PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/venv" ]; then
    print_error "Virtual environment not found at $PROJECT_DIR/venv"
    print_info "Please create virtual environment first:"
    print_info "  cd $PROJECT_DIR"
    print_info "  python3 -m venv venv"
    print_info "  source venv/bin/activate"
    print_info "  pip install -r requirements.txt"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    print_error ".env file not found at $PROJECT_DIR/.env"
    print_info "Please create .env file from .env.dist template"
    exit 1
fi

# Create necessary directories
print_info "Creating necessary directories..."
mkdir -p /var/run/celery
mkdir -p /var/log/celery
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/media"

# Set ownership
print_info "Setting directory ownership..."
chown -R $SERVICE_USER:$SERVICE_GROUP /var/run/celery
chown -R $SERVICE_USER:$SERVICE_GROUP /var/log/celery
chown -R $SERVICE_USER:$SERVICE_GROUP "$PROJECT_DIR/logs"
chown -R $SERVICE_USER:$SERVICE_GROUP "$PROJECT_DIR/media"

# Update service files with actual project directory
print_info "Updating service files with project directory..."
for service_file in "$SCRIPT_DIR/systemd"/*.service; do
    if [ -f "$service_file" ]; then
        sed -i "s|/opt/i-tat-bot|$PROJECT_DIR|g" "$service_file"
    fi
done

# Copy service files to systemd directory
print_info "Installing systemd service files..."
cp "$SCRIPT_DIR/systemd/i-tat-bot.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/systemd/i-tat-celery-worker.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/systemd/i-tat-celery-beat.service" "$SYSTEMD_DIR/"

# Set correct permissions
chmod 644 "$SYSTEMD_DIR/i-tat-bot.service"
chmod 644 "$SYSTEMD_DIR/i-tat-celery-worker.service"
chmod 644 "$SYSTEMD_DIR/i-tat-celery-beat.service"

# Reload systemd daemon
print_info "Reloading systemd daemon..."
systemctl daemon-reload

# Enable services
print_info "Enabling services to start on boot..."
systemctl enable i-tat-bot.service
systemctl enable i-tat-celery-worker.service
systemctl enable i-tat-celery-beat.service

print_info "✅ Services installed successfully!"
echo ""
print_info "Available commands:"
echo "  Start all services:"
echo "    sudo systemctl start i-tat-bot"
echo "    sudo systemctl start i-tat-celery-worker"
echo "    sudo systemctl start i-tat-celery-beat"
echo ""
echo "  Stop all services:"
echo "    sudo systemctl stop i-tat-celery-beat"
echo "    sudo systemctl stop i-tat-celery-worker"
echo "    sudo systemctl stop i-tat-bot"
echo ""
echo "  Restart services:"
echo "    sudo systemctl restart i-tat-bot"
echo "    sudo systemctl restart i-tat-celery-worker"
echo "    sudo systemctl restart i-tat-celery-beat"
echo ""
echo "  Check status:"
echo "    sudo systemctl status i-tat-bot"
echo "    sudo systemctl status i-tat-celery-worker"
echo "    sudo systemctl status i-tat-celery-beat"
echo ""
echo "  View logs:"
echo "    sudo journalctl -u i-tat-bot -f"
echo "    sudo journalctl -u i-tat-celery-worker -f"
echo "    sudo journalctl -u i-tat-celery-beat -f"
echo ""

read -p "Do you want to start the services now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting services..."
    systemctl start i-tat-bot
    sleep 2
    systemctl start i-tat-celery-worker
    sleep 2
    systemctl start i-tat-celery-beat
    
    echo ""
    print_info "Service status:"
    systemctl status i-tat-bot --no-pager -l
    echo ""
    systemctl status i-tat-celery-worker --no-pager -l
    echo ""
    systemctl status i-tat-celery-beat --no-pager -l
fi

print_info "Setup complete!"
