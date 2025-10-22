# GrowSense Deployment Guide

## Deploying to Render (Free Tier)

### Prerequisites
- GitHub account with GrowSense repository
- Render account (sign up at https://render.com - free tier available)
- Firebase project with Firestore enabled
- Firebase service account JSON file

---

## Step 1: Prepare Your Firebase Credentials

### Get Service Account JSON as a Single Line

Run this command locally to convert your service account JSON to a single line:

```bash
cat serviceAccountKey.json | tr -d '\n' | tr -d ' '
```

Copy the output - you'll paste this into Render as an environment variable.

---

## Step 2: Create a New Web Service on Render

1. Go to https://dashboard.render.com/
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account if you haven't already
4. Select your **GrowSense** repository
5. Configure the service:

### Basic Settings
- **Name**: `growsense` (or your preferred name)
- **Region**: Choose closest to you (e.g., Oregon, Ohio)
- **Branch**: `main`
- **Root Directory**: (leave empty)
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 "app:create_app()"`

### Plan
- Select **Free** tier

---

## Step 3: Set Environment Variables

In the Render dashboard, scroll down to **Environment Variables** and add:

### Required Variables

| Key | Value | Notes |
|-----|-------|-------|
| `FLASK_ENV` | `production` | Sets Flask to production mode |
| `PYTHON_VERSION` | `3.10.13` | Python version |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | `{paste single-line JSON here}` | Your Firebase credentials (from Step 1) |
| `DEVICE_KEYS_PATH` | `./device_keys.json` | Path to device API keys |

### Optional Variables

| Key | Value | Notes |
|-----|-------|-------|
| `FIREBASE_STORAGE_BUCKET` | `growsense-1cdec.appspot.com` | For image uploads (replace with your bucket) |

**Important**: Mark `FIREBASE_SERVICE_ACCOUNT_JSON` as a **Secret** by clicking the lock icon.

---

## Step 4: Deploy

1. Click **"Create Web Service"** at the bottom
2. Render will automatically:
   - Clone your repository
   - Install dependencies from `requirements.txt`
   - Start the app with gunicorn

This takes about 5-10 minutes for the first deploy.

---

## Step 5: Test Your Deployed App

Once deployed, Render will give you a URL like:
```
https://growsense.onrender.com
```

### Test the Health Endpoint

```bash
curl https://growsense.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "GrowSense API",
  "timestamp": "2024-10-22T12:34:56.789012Z"
}
```

### Test Upload from ESP32 (or curl)

```bash
curl -X POST https://growsense.onrender.com/upload_data \
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

### View Dashboard

Open in browser:
```
https://growsense.onrender.com
```

---

## Step 6: Keep Your App Warm (Free Tier)

Render's free tier spins down after 15 minutes of inactivity. This causes **cold starts** (30-60 second delay on first request).

### Option A: UptimeRobot (Recommended)

1. Sign up at https://uptimerobot.com (free)
2. Create a new monitor:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: GrowSense
   - **URL**: `https://growsense.onrender.com/health`
   - **Monitoring Interval**: 5 minutes
3. Save - UptimeRobot will ping your app every 5 minutes to keep it warm

### Option B: Cron-job.org

1. Sign up at https://cron-job.org
2. Create a new cron job:
   - **URL**: `https://growsense.onrender.com/health`
   - **Schedule**: Every 5 minutes
3. Enable the job

**Note**: Free tier has limited hours per month (~750 hours). If you exceed this, the app will sleep until next month.

---

## Step 7: Update ESP32 Code

Update your ESP32 firmware to use the Render URL:

```cpp
const char* serverUrl = "https://growsense.onrender.com/upload_data";
```

---

## Troubleshooting

### Build Failed
- Check that `requirements.txt` is in the root directory
- Verify Python version in `runtime.txt` is supported by Render
- Check build logs in Render dashboard for specific errors

### App Crashes on Start
- Verify all environment variables are set correctly
- Check that `FIREBASE_SERVICE_ACCOUNT_JSON` is valid JSON (no extra quotes or escape characters)
- Review application logs in Render dashboard

### 403 Firestore Error
- Ensure Firestore API is enabled in Firebase Console
- Verify service account JSON has correct permissions
- Check that the Firebase project ID in the JSON matches your project

### Slow First Request (Cold Start)
- This is normal for free tier
- Set up UptimeRobot to ping every 5 minutes
- Consider upgrading to paid tier for always-on service

### Device Upload Fails
- Verify `device_id` exists in `device_keys.json`
- Check that `api_key` matches the one in `device_keys.json`
- Ensure ESP32 has internet connectivity
- Test with curl first to verify the endpoint works

---

## Updating Your Deployment

When you push changes to GitHub:

1. Commit and push to `main` branch
2. Render automatically detects the push
3. Render rebuilds and redeploys (takes 2-5 minutes)
4. Your app is updated!

**Manual Deploy**: In Render dashboard, click **"Manual Deploy"** → **"Deploy latest commit"**

---

## Monitoring & Logs

### View Logs
1. Go to Render dashboard
2. Select your GrowSense service
3. Click **"Logs"** tab
4. See real-time application logs

### Useful Log Filters
- `GET /health` - Health check pings
- `POST /upload_data` - Sensor data uploads
- `Error` - Application errors
- `Firebase` - Firebase connection issues

---

## Cost Considerations

### Free Tier Limits
- ✅ 750 hours/month of uptime
- ✅ Spins down after 15 minutes of inactivity
- ✅ Shared CPU/memory
- ✅ 100GB bandwidth/month

### When to Upgrade
- If you need 24/7 uptime without cold starts
- If you exceed free tier hours
- If you need faster response times
- If you have multiple devices sending data frequently

Paid plans start at $7/month for always-on service.

---

## Next Steps

After deployment:
1. ✅ Test uploads from ESP32
2. ✅ Set up UptimeRobot monitoring
3. ✅ Add more devices to `device_keys.json`
4. Consider adding authentication for dashboard access
5. Consider adding data export features
6. Consider implementing Firebase Cloud Functions for advanced features

---

## Security Recommendations

### Production Checklist
- [x] Firebase service account JSON stored as Render secret
- [x] Device API keys not committed to git
- [x] Firestore in production mode (denies direct client access)
- [ ] Add rate limiting to prevent API abuse
- [ ] Add HTTPS-only enforcement (Render does this automatically)
- [ ] Add dashboard authentication (future enhancement)
- [ ] Rotate API keys periodically
- [ ] Monitor logs for suspicious activity

---

## Support

If you encounter issues:
1. Check Render logs for errors
2. Verify Firebase Console for quota/usage
3. Test endpoints with curl before using ESP32
4. Review this guide's troubleshooting section

For Render-specific issues, see: https://render.com/docs

