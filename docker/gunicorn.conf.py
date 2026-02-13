"""
Gunicorn configuration for WireGuard Auto
Socket-based deployment for use with nginx reverse proxy
"""

import os
import multiprocessing

# Server socket
bind = "unix:/home/tisp/wg-auto/run/gunicorn.sock"
backlog = 2048

# Process naming
proc_name = "wireguard-auto"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/home/tisp/wg-auto/logs/access.log"
errorlog = "/home/tisp/wg-auto/logs/error.log"
loglevel = "info"

# Application
pythonpath = "/home/tisp/wg-auto"
wsgi_app = "config.wsgi:application"

# Security and performance
max_requests = 1000
max_requests_jitter = 50
