# How to Enable Google Sign-In in Firebase Console

Authentication **IS available** on the Spark (free) plan! Here's how to find it:

## Method 1: Direct Link (Easiest)

1. Go directly to this URL (replace `growsense-1cdec` with your project ID if different):
   ```
   https://console.firebase.google.com/project/growsense-1cdec/authentication/providers
   ```

2. You should see a list of sign-in providers
3. Click on **"Google"**
4. Toggle **"Enable"** to ON
5. Set a **Project support email** (your email)
6. Click **"Save"**

## Method 2: Through Firebase Console Navigation

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: **growsense-1cdec**
3. Look at the **left sidebar menu** - you should see:
   - Build
     - Authentication ← **Click here!**
     - Firestore Database
     - Storage
     - etc.

4. If you don't see "Authentication" in the sidebar:
   - It might be collapsed under "Build"
   - Click the "Build" section to expand it
   - Or look for it in the main dashboard

5. Once in Authentication:
   - Click the **"Sign-in method"** tab (at the top)
   - You'll see a list of providers
   - Click on **"Google"**
   - Toggle **"Enable"** to ON
   - Set **Project support email**
   - Click **"Save"**

## Method 3: If Authentication Section is Missing

If you truly don't see Authentication anywhere, it might not be enabled for your project yet:

1. Go to: https://console.firebase.google.com/project/growsense-1cdec/overview
2. Look for a banner or message about enabling additional features
3. Or try creating a new Firebase project and enabling Authentication there first

## Quick Test After Enabling

1. Restart your Flask server (if it's running)
2. Visit `http://localhost:5001`
3. Click "Sign in with Google"
4. You should see the Google sign-in popup

## Troubleshooting

**If you still can't find Authentication:**
- Make sure you're logged into the correct Google account
- Try a different browser
- Check if you have the correct permissions on the Firebase project
- The direct link method (Method 1) usually works best

**Common Issues:**
- "Authentication not enabled" - You might need to wait a few minutes after enabling
- "Invalid API key" - Make sure your FIREBASE_WEB_CONFIG is correct
- "Domain not authorized" - Add `localhost` to authorized domains in Firebase Console

## Authorized Domains

After enabling Google sign-in, make sure `localhost` is in your authorized domains:

1. Go to: Authentication → Settings → Authorized domains
2. Make sure `localhost` is listed (it should be by default)
3. For production, add your Render domain (e.g., `your-app.onrender.com`)

