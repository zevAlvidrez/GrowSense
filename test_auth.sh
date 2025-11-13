#!/bin/bash
# Test script for authentication endpoints
# Note: You'll need a valid Firebase ID token to test these endpoints

BASE_URL="${1:-http://localhost:5000}"

echo "🧪 Testing GrowSense Authentication Endpoints"
echo "=============================================="
echo "Base URL: $BASE_URL"
echo ""

# Test 1: Health check (should work without auth)
echo "1. Testing /health endpoint (no auth required)..."
curl -s -X GET "$BASE_URL/health" | python3 -m json.tool
echo ""
echo ""

# Test 2: /auth/login with missing token
echo "2. Testing /auth/login with missing token (should fail)..."
curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
echo ""
echo ""

# Test 3: /auth/login with invalid token
echo "3. Testing /auth/login with invalid token (should fail)..."
curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"id_token": "invalid-token-12345"}' | python3 -m json.tool
echo ""
echo ""

# Test 4: /auth/me without token (should fail)
echo "4. Testing /auth/me without Authorization header (should fail)..."
curl -s -X GET "$BASE_URL/auth/me" | python3 -m json.tool
echo ""
echo ""

# Test 5: /auth/me with invalid token (should fail)
echo "5. Testing /auth/me with invalid token (should fail)..."
curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer invalid-token-12345" | python3 -m json.tool
echo ""
echo ""

echo "=============================================="
echo "✅ Basic endpoint tests complete!"
echo ""
echo "📝 To test with a valid token:"
echo "   1. Get a Firebase ID token from your frontend"
echo "   2. Run: curl -X POST $BASE_URL/auth/login \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"id_token\": \"YOUR_TOKEN_HERE\"}'"
echo ""
echo "   3. Or test /auth/me:"
echo "      curl -X GET $BASE_URL/auth/me \\"
echo "        -H 'Authorization: Bearer YOUR_TOKEN_HERE'"
echo ""

