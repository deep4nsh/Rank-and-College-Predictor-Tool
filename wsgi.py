"""
WSGI / ASGI bridge entrypoint for cloud PaaS runners (Render, Railway, Heroku).
"""

from backend.app.main import app

# Export app as both application and app
application = app
