#!/usr/bin/env python3
"""
GrowSense Flask application entry point.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🌱 GrowSense server starting on http://localhost:{port}")
    print(f"   Debug mode: {debug}")
    print(f"   Press CTRL+C to quit\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

