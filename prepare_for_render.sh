#!/bin/bash
# Helper script to prepare Firebase credentials for Render deployment

echo "🚀 GrowSense - Render Deployment Helper"
echo "========================================"
echo ""

# Check if serviceAccountKey.json exists
if [ ! -f "serviceAccountKey.json" ]; then
    echo "❌ Error: serviceAccountKey.json not found in current directory"
    echo "   Please make sure you're in the GrowSense project root"
    exit 1
fi

echo "✅ Found serviceAccountKey.json"
echo ""
echo "Converting to single-line format for Render..."
echo ""
echo "================================================"
echo "COPY THIS VALUE FOR FIREBASE_SERVICE_ACCOUNT_JSON:"
echo "================================================"
echo ""

# Convert to single line (remove all newlines and extra spaces)
cat serviceAccountKey.json | tr -d '\n' | tr -s ' ' ' '

echo ""
echo ""
echo "================================================"
echo ""
echo "📋 Next Steps:"
echo "1. Copy the JSON above (entire line)"
echo "2. Go to your Render dashboard"
echo "3. Add environment variable: FIREBASE_SERVICE_ACCOUNT_JSON"
echo "4. Paste the JSON as the value"
echo "5. Mark it as 'Secret' (click the lock icon)"
echo ""
echo "See DEPLOYMENT.md for complete deployment instructions"
echo ""

