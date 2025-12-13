# GrowSense

A complete IoT plant monitoring system that collects sensor data from ESP32 modules and provides an intelligent dashboard with AI-powered plant care advice.

## Overview

GrowSense is a full-stack IoT solution for monitoring plant health through environmental sensors. The system consists of ESP32-based sensor modules that collect temperature, humidity, light, soil moisture, and UV index data, which is then visualized in a web dashboard and analyzed by Google's Gemini AI to provide personalized plant care recommendations.

### What Problem Does It Solve?

Traditional plant care relies on guesswork and manual monitoring. GrowSense automates data collection and provides:
- **Real-time monitoring** of critical environmental factors
- **Historical trend analysis** to understand plant needs over time
- **AI-powered insights** that translate sensor data into actionable advice
- **Multi-device support** for monitoring multiple plants or locations

## Features

- **Multi-Sensor Data Collection**: Temperature, humidity, light intensity, soil moisture, and UV index
- **Real-Time Dashboard**: Interactive charts and tables showing current and historical sensor readings
- **AI Plant Care Advice**: Personalized recommendations powered by Google Gemini AI based on your sensor data
- **User-Centric Architecture**: Secure Firebase authentication with per-user device management
- **Efficient Caching System**: Reduces database reads by 95-97% while maintaining real-time updates
- **Low-Power Firmware**: ESP32 modules use deep sleep for 6-12 month battery life
- **Cloud-Based**: Scalable Firebase backend with automatic data synchronization

## Architecture Overview

GrowSense consists of three main components:

### 1. ESP32 Firmware (`firmware/`)
- Collects sensor data from 4 sensors (AM2320, BH1750, SEN0193, GUVA-S12SD)
- Uploads data to cloud via HTTP POST requests
- Implements deep sleep for ultra-low power consumption
- Configurable sampling intervals (30s to 10 minutes)

### 2. Flask Backend (`app/`)
- RESTful API for device registration and data upload
- Firebase Authentication for secure user access
- Multi-tier caching system (server-side + client-side localStorage)
- Gemini AI integration for plant care advice generation
- User-centric data organization in Firestore

### 3. Web Dashboard (`app/static/` & `app/templates/`)
- Real-time data visualization with Chart.js
- Device management interface
- AI advice display with device-specific recommendations
- Responsive design for desktop and mobile

## Quick Start

### Prerequisites

- Python 3.10+
- Firebase project with Firestore and Authentication enabled
- Firebase service account JSON file
- Firebase web app configuration
- ESP32 development board
- Arduino IDE with ESP32 board support

### Backend Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/GrowSense.git
cd GrowSense
```

2. **Set up Python virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment variables**

Create a `.env` file:
```bash
# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json
# OR use JSON string for cloud deployment:
FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'

FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}'

# Flask Configuration
FLASK_ENV=development
PORT=5001
```

**Getting Firebase Web Config:**
- Go to [Firebase Console](https://console.firebase.google.com/)
- Project Settings → Your apps → Web app
- Copy the `firebaseConfig` object

4. **Enable Google Sign-In**
- Firebase Console → Authentication → Sign-in method
- Enable Google provider

5. **Run the server**
```bash
source venv/bin/activate
python run.py
```

6. **Open dashboard**
```
http://localhost:5001
```

### Firmware Setup

See [firmware/README.md](firmware/README.md) for complete ESP32 setup instructions.

## Implementation Details

### Caching Architecture

GrowSense uses a multi-tier caching system to minimize Firestore read operations:

**Frontend Cache (Browser):**
- In-memory cache for fast access during session
- localStorage persistence for instant page loads
- Incremental updates (only fetch new readings since last check)
- Stores 120 recent high-resolution readings per device
- Stores 120 historical samples (one per hour) for trend visualization

**Server-Side Cache:**
- In-memory cache with 24-hour TTL
- Populated automatically when devices upload data
- Used primarily for Gemini AI analysis (no database queries needed)
- Stores device metadata and analysis history

**Result:** Reduces Firestore reads by 95-97% compared to naive implementation, staying well within Firebase free tier limits even with multiple devices and frequent dashboard access.

### Device Registration Workflow

1. **User Registration:**
   - User signs in with Google via Firebase Authentication
   - User ID is stored for device ownership

2. **Device Registration:**
   - User registers device via `/devices/register` endpoint
   - Device ID and API key are stored in Firestore
   - Device is linked to user in `/users/{userId}/devices/{deviceId}`
   - Reverse lookup created in `/devices/{deviceId}` for fast API key validation

3. **Data Upload:**
   - ESP32 sends POST request to `/upload_data` with device_id and api_key
   - Server validates API key against Firestore
   - Reading is stored in `/users/{userId}/devices/{deviceId}/readings/{readingId}`
   - Server cache is updated with new reading

4. **Data Access:**
   - User requests data via `/user_data` endpoint (requires authentication)
   - Server returns readings from user's devices only
   - Frontend caches data in localStorage for subsequent loads

### Deployment

GrowSense can be deployed to any platform that supports Python/Flask. The repository includes configuration for Render.com free tier.

**Render Deployment Steps:**

1. **Prepare Firebase Credentials:**
   - Convert service account JSON to single line:
     ```bash
     cat serviceAccountKey.json | tr -d '\n' | tr -d ' '
     ```

2. **Create Web Service on Render:**
   - Connect GitHub repository
   - Select Python environment
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 "app:create_app()"`

3. **Set Environment Variables:**
   - `FIREBASE_SERVICE_ACCOUNT_JSON` - Single-line JSON string
   - `FIREBASE_WEB_CONFIG` - Firebase web config JSON string
   - `GOOGLE_API_KEY` or `GEMINI_API_KEY` - For AI advice feature

4. **Update Firmware:**
   - Change `SERVER_URL` in firmware to your Render URL
   - Re-upload firmware to ESP32 devices

See `render.yaml` for automated deployment configuration.

## Project Structure

```
GrowSense/
├── app/                    # Flask backend application
│   ├── __init__.py        # Flask app factory
│   ├── routes.py          # API endpoints
│   ├── firebase_client.py # Firebase operations
│   ├── gemini_client.py   # AI advice generation
│   ├── cache.py           # Server-side caching
│   ├── static/            # Frontend assets
│   │   ├── main.js       # Dashboard JavaScript
│   │   └── style.css     # Dashboard styles
│   └── templates/         # HTML templates
│       └── index.html    # Main dashboard
├── firmware/              # ESP32 Arduino sketches
│   ├── GrowSenseModule_Production/  # Production firmware
│   ├── Adafruit_AM2320.ino          # Temp/Humidity test
│   ├── BH1750_Light_Sensor.ino      # Light sensor test
│   ├── SEN0193_Soil_Moister_Sensor.ino  # Soil moisture test
│   └── GUVA-S12SD_UV_Sensor.ino     # UV sensor test
├── scripts/               # Utility scripts
│   ├── analyze_*.js      # Data analysis scripts
│   ├── check_firestore_data.py
│   └── export_device_data.py
├── requirements.txt       # Python dependencies
├── Procfile              # Process configuration
├── render.yaml           # Render deployment config
└── README.md            # This file
```

## API Reference

### Authentication Endpoints

- `POST /auth/login` - Verify Firebase ID token
- `GET /auth/me` - Get current user info (requires auth)
- `POST /auth/logout` - Logout (requires auth)

### Device Management

- `POST /devices/register` - Register device to user (requires auth)
- `GET /devices` - List user's devices (requires auth)
- `GET /devices/<device_id>` - Get device info (requires auth)
- `POST /devices/<device_id>/config` - Update device config (requires auth)
- `POST /devices/<device_id>/description` - Update device description (requires auth)
- `DELETE /devices/<device_id>` - Remove device (requires auth)

### Data Endpoints

- `POST /upload_data` - Upload sensor reading (device API key auth)
- `GET /user_data` - Get all user's readings (requires auth)
  - Query param `since`: ISO timestamp for incremental updates
- `GET /user_data/<device_id>` - Get device-specific readings (requires auth)
- `GET /user_advice` - Get AI plant care advice (requires auth)

### Health

- `GET /health` - Health check endpoint

## Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: Firebase Cloud Firestore
- **Authentication**: Firebase Authentication (Google Sign-In)
- **AI**: Google Gemini API
- **Frontend**: Vanilla JavaScript, Chart.js
- **Firmware**: Arduino/ESP32
- **Deployment**: Render.com (or any Python hosting)

## License

See LICENSE file in repository.
