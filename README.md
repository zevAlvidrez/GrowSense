# GrowSense MVP

A minimal Flask web application that accepts sensor data from ESP32 modules and stores it in Firebase Cloud Firestore, with a simple dashboard for viewing data.

## Project Structure

```
GrowSense/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py            # API endpoints (to be added)
│   ├── firebase_client.py   # Firebase initialization (to be added)
│   ├── templates/           # HTML templates
│   │   └── index.html       # Dashboard (to be added)
│   └── static/              # Static assets
│       └── main.js          # Frontend JS (to be added)
├── requirements.txt         # Python dependencies
├── .gitignore              # Git ignore patterns
├── .env                    # Environment variables (NOT committed)
└── README.md               # This file
```

## Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: Firebase Cloud Firestore
- **Storage**: Firebase Storage (optional)
- **Hosting**: Render (free tier)
- **Authentication**: Simple API key validation (MVP)

## Setup Instructions

(To be added in subsequent steps)

## Running Locally

### Quick Start

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
```bash
# Create .env file (see .env.example)
cp .env.example .env

# Edit .env and add your Firebase credentials
# FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json
```

4. **Run the server**
```bash
PORT=5001 python3 run.py
# Or simply: python3 run.py (defaults to port 5000)
```

5. **Open dashboard**
```
http://localhost:5001
```

### Testing the API

Run the test script:
```bash
./test_api.sh
```

Or manually test with curl:
```bash
curl -X POST http://localhost:5001/upload_data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_device",
    "api_key": "test-key-12345",
    "temperature": 23.5,
    "humidity": 65.2,
    "light": 450,
    "soil_moisture": 42.1
  }'
```

## Deployment

### Deploy to Render (Free Tier)

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for complete deployment guide.

**Quick steps:**
1. Run `./prepare_for_render.sh` to get Firebase credentials in correct format
2. Create new Web Service on Render.com
3. Connect your GitHub repository
4. Set environment variables (see DEPLOYMENT.md)
5. Deploy!

Your app will be live at: `https://your-app-name.onrender.com`

### Keep App Warm (Free Tier)

Free tier spins down after 15 minutes. Use [UptimeRobot](https://uptimerobot.com) to ping `/health` every 5 minutes.

## License

(See LICENSE file in repository)
