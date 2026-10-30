# Gunicorn settings for the ship-booking systemd service.
bind = "127.0.0.1:8001"  # only Nginx talks to Gunicorn
workers = 3  # roughly 2 x CPU cores + 1; raise on a bigger server
timeout = 30
accesslog = "-"  # stdout -> journald
errorlog = "-"
forwarded_allow_ips = "127.0.0.1"
