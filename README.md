# GrowSense

A Flask web application for monitoring plant sensors from ESP32 modules. Features Firebase Authentication, user-centric device management, and AI-powered plant care advice.

## Features

- 🔐 **Firebase Authentication** - Secure Google sign-in for users
- 📱 **Multi-Device Dashboard** - Monitor up to 4 devices per user with individual charts
- 📊 **Real-time Data Visualization** - Charts and tables for temperature, humidity, light, and soil moisture
- 🤖 **AI Plant Care Advice** - Get personalized recommendations from Gemini AI
- ☁️ **Firebase Cloud Firestore** - Scalable cloud database
- 🚀 **Render Deployment** - Easy deployment to Render free tier

## Project Structure

```
GrowSense/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py            # API endpoints
│   ├── firebase_client.py   # Firebase initialization & helpers
│   ├── gemini_client.py     # Gemini AI integration (placeholder)
│   ├── templates/
│   │   └── index.html       # Dashboard UI
│   └── static/
│       ├── main.js          # Frontend JavaScript
│       └── style.css        # Dashboard styles
├── firmware/                # ESP32 firmware code
├── scripts/                 # Utility scripts
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: Firebase Cloud Firestore
- **Authentication**: Firebase Authentication (Google Sign-In)
- **AI**: Google Gemini (for plant care advice)
- **Hosting**: Render (free tier)

## Quick Start

### Prerequisites

- Python 3.10+
- Firebase project with Firestore and Authentication enabled
- Firebase service account JSON file
- Firebase web app configuration

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/zevAlvidrez/GrowSense.git
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
FIREBASE_WEB_CONFIG={"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}

# Flask Configuration
FLASK_ENV=development
PORT=5001
```

**Getting Firebase Web Config:**
- Go to [Firebase Console](https://console.firebase.google.com/)
- Project Settings → Your apps → Web app
- Copy the `firebaseConfig` object
- See `FIREBASE_WEB_CONFIG_SETUP.md` for detailed instructions

4. **Enable Google Sign-In**
- Firebase Console → Authentication → Sign-in method
- Enable Google provider
- See `ENABLE_GOOGLE_AUTH.md` for details

5. **Run the server**
```bash
source venv/bin/activate
python run.py
```

6. **Open dashboard**
```
http://localhost:5001
```

## Usage

### Registering Devices

1. Sign in to the dashboard with Google
2. Register devices via API:
```bash
curl -X POST http://localhost:5001/devices/register \
  -H "Authorization: Bearer <FIREBASE_ID_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32_device_001",
    "api_key": "your-secret-key",
    "name": "Living Room Sensor"
  }'
```

3. Add device to `device_keys.json`:
```json
{
  "esp32_device_001": { "api_key": "your-secret-key" }
}
```

### Uploading Sensor Data

ESP32 devices can upload data via:
```bash
curl -X POST http://localhost:5001/upload_data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32_device_001",
    "api_key": "your-secret-key",
    "temperature": 23.5,
    "humidity": 65.2,
    "light": 450,
    "soil_moisture": 42.1
  }'
```

### Getting AI Advice

Click the "Get Advice" button in the dashboard to receive personalized plant care recommendations based on your sensor data.

## API Endpoints

### Authentication
- `POST /auth/login` - Verify Firebase ID token
- `GET /auth/me` - Get current user info (requires auth)
- `POST /auth/logout` - Logout (requires auth)

### Device Management
- `POST /devices/register` - Register device to user (requires auth)
- `GET /devices` - List user's devices (requires auth)
- `GET /devices/<device_id>` - Get device info (requires auth)
- `DELETE /devices/<device_id>` - Remove device (requires auth)

### Data
- `POST /upload_data` - Upload sensor reading (device API key auth)
- `GET /user_data` - Get all user's readings (requires auth)
- `GET /user_data/<device_id>` - Get device-specific readings (requires auth)
- `GET /user_advice` - Get AI plant care advice (requires auth)

### Health
- `GET /health` - Health check endpoint

## Testing

See test scripts:
- `test_auth.sh` - Test authentication endpoints
- `test_devices.sh` - Test device management
- `test_api.sh` - Test data upload

## Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for complete deployment guide to Render.

**Quick steps:**
1. Push code to GitHub
2. Create Web Service on Render.com
3. Set environment variables (including `FIREBASE_WEB_CONFIG`)
4. Deploy!

## Documentation

- `DEPLOYMENT.md` - Render deployment guide
- `FIREBASE_WEB_CONFIG_SETUP.md` - Firebase web config setup
- `ENABLE_GOOGLE_AUTH.md` - Enable Google sign-in
- `firmware/README.md` - ESP32 firmware setup

## License

See LICENSE file in repository.
