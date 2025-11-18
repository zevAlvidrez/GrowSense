# Firebase Web Config Setup Guide

The frontend needs a Firebase web configuration to enable Google sign-in. This is different from the service account key (which is for backend/server-side).

## Step 1: Get Firebase Web Config from Firebase Console

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (the same one you're using for Firestore)
3. Click the gear icon ⚙️ next to "Project Overview"
4. Select **"Project settings"**
5. Scroll down to **"Your apps"** section
6. If you don't have a web app yet:
   - Click the **`</>`** (Web) icon
   - Register your app with a nickname (e.g., "GrowSense Web")
   - Click "Register app"
7. Copy the `firebaseConfig` object. It looks like this:

```javascript
const firebaseConfig = {
  apiKey: "AIzaSy...",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abcdef"
};
```

## Step 2: Convert to JSON String

Convert the config object to a single-line JSON string. You can use this Python command:

```bash
python3 -c "import json; config = {'apiKey': 'AIzaSy...', 'authDomain': 'your-project.firebaseapp.com', 'projectId': 'your-project-id', 'storageBucket': 'your-project.appspot.com', 'messagingSenderId': '123456789', 'appId': '1:123456789:web:abcdef'}; print(json.dumps(config))"
```

Or manually format it as:
```json
{"apiKey":"AIzaSy...","authDomain":"your-project.firebaseapp.com","projectId":"your-project-id","storageBucket":"your-project.appspot.com","messagingSenderId":"123456789","appId":"1:123456789:web:abcdef"}
```

## Step 3: Set Environment Variable

### For Local Development:

Add to your `.env` file (or export in terminal):
```bash
export FIREBASE_WEB_CONFIG='{"apiKey":"AIzaSy...","authDomain":"your-project.firebaseapp.com","projectId":"your-project-id","storageBucket":"your-project.appspot.com","messagingSenderId":"123456789","appId":"1:123456789:web:abcdef"}'
```

Or add to `.env`:
```
FIREBASE_WEB_CONFIG={"apiKey":"AIzaSy...","authDomain":"your-project.firebaseapp.com","projectId":"your-project-id","storageBucket":"your-project.appspot.com","messagingSenderId":"123456789","appId":"1:123456789:web:abcdef"}
```

### For Production (Render):

Add `FIREBASE_WEB_CONFIG` as an environment variable in Render dashboard with the JSON string value.

## Step 4: Enable Google Sign-In

1. In Firebase Console, go to **Authentication** → **Sign-in method**
2. Click on **Google**
3. Enable it and set a support email
4. Save

## Step 5: Restart Server

After setting the environment variable, restart your Flask server:

```bash
# Stop the current server (Ctrl+C)
# Then restart:
source venv/bin/activate
python run.py
```

## Quick Test

After setup, visit `http://localhost:5001` and you should see the login modal. Click "Sign in with Google" to test authentication.

