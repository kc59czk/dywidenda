# Simple Gunicorn configuration file with sensible defaults for this app.
# Adjust `workers` and `threads` according to your deployment environment.

bind = '0.0.0.0:8000'
workers = 2
threads = 4
timeout = 30

# Log to stdout/stderr so container platforms can capture logs
accesslog = '-'
errorlog = '-'
loglevel = 'info'
