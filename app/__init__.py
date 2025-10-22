"""
GrowSense Flask Application
Handles sensor data ingestion from ESP32 modules and displays dashboard.
"""

from flask import Flask

def create_app():
    """Application factory pattern for Flask app."""
    app = Flask(__name__)
    
    # Register routes
    from app import routes
    app.register_blueprint(routes.bp)
    
    return app

