#!/bin/bash
# Helper script to set up Firebase Web Config

echo "🌱 GrowSense Firebase Web Config Setup"
echo "========================================"
echo ""
echo "This script will help you set up the FIREBASE_WEB_CONFIG environment variable."
echo ""
echo "Step 1: Get your Firebase Web Config"
echo "--------------------------------------"
echo "1. Go to: https://console.firebase.google.com/"
echo "2. Select your project: growsense-1cdec"
echo "3. Click ⚙️ (gear icon) → Project settings"
echo "4. Scroll to 'Your apps' section"
echo "5. If no web app exists, click '</>' icon to add one"
echo "6. Copy the firebaseConfig object"
echo ""
echo "The config should look like:"
echo '  const firebaseConfig = {'
echo '    apiKey: "AIzaSy...",'
echo '    authDomain: "growsense-1cdec.firebaseapp.com",'
echo '    projectId: "growsense-1cdec",'
echo '    storageBucket: "growsense-1cdec.appspot.com",'
echo '    messagingSenderId: "123456789",'
echo '    appId: "1:123456789:web:abcdef"'
echo '  };'
echo ""
read -p "Press Enter when you have the config ready..."

echo ""
echo "Step 2: Enter your Firebase config values"
echo "------------------------------------------"
read -p "Enter apiKey: " API_KEY
read -p "Enter authDomain: " AUTH_DOMAIN
read -p "Enter projectId: " PROJECT_ID
read -p "Enter storageBucket: " STORAGE_BUCKET
read -p "Enter messagingSenderId: " MESSAGING_SENDER_ID
read -p "Enter appId: " APP_ID

# Create JSON string
FIREBASE_WEB_CONFIG=$(python3 -c "
import json
config = {
    'apiKey': '$API_KEY',
    'authDomain': '$AUTH_DOMAIN',
    'projectId': '$PROJECT_ID',
    'storageBucket': '$STORAGE_BUCKET',
    'messagingSenderId': '$MESSAGING_SENDER_ID',
    'appId': '$APP_ID'
}
print(json.dumps(config))
")

echo ""
echo "Step 3: Setting environment variable"
echo "------------------------------------"
echo "Adding to .env file..."

# Check if .env exists, create if not
if [ ! -f .env ]; then
    touch .env
    echo "Created .env file"
fi

# Remove old FIREBASE_WEB_CONFIG if exists
sed -i.bak '/^FIREBASE_WEB_CONFIG=/d' .env 2>/dev/null || true

# Add new config
echo "FIREBASE_WEB_CONFIG='$FIREBASE_WEB_CONFIG'" >> .env

echo ""
echo "✅ Firebase Web Config added to .env file!"
echo ""
echo "Step 4: Enable Google Sign-In"
echo "------------------------------"
echo "1. Go to: https://console.firebase.google.com/project/growsense-1cdec/authentication/providers"
echo "2. Click on 'Google'"
echo "3. Enable it and set a support email"
echo "4. Save"
echo ""
echo "Step 5: Restart your server"
echo "----------------------------"
echo "Stop the current server (Ctrl+C) and restart with:"
echo "  source venv/bin/activate"
echo "  python run.py"
echo ""
echo "Or if using .env file, make sure to load it:"
echo "  source venv/bin/activate"
echo "  export \$(cat .env | xargs)"
echo "  python run.py"
echo ""
echo "After restarting, visit http://localhost:5001 to test login!"

