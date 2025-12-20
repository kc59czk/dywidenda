"""WSGI entrypoint for Gunicorn.

Usage: gunicorn -c gunicorn_config.py wsgi:app
"""
from app import create_app

# Create the Flask application. Gunicorn will import this module and look for
# the `app` callable.
app = create_app()

# Some PaaS platforms expect `application` as the callable name.
application = app
