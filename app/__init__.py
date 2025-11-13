"""
GrowSense Flask Application
Handles sensor data ingestion from ESP32 modules and displays dashboard.
"""

from flask import Flask
from flask_cors import CORS

def create_app():
    """Application factory pattern for Flask app."""
    app = Flask(__name__)
    
    # Enable CORS for all routes (needed for frontend auth)
    # In production, you may want to restrict origins
    CORS(app, resources={
        r"/*": {
            "origins": "*",  # Allow all origins (adjust for production)
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Register routes
    from app import routes
    app.register_blueprint(routes.bp)
    
    return app

