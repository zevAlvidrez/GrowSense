# GrowSense Caching Architecture

## Overview

This document explains the caching system implemented in GrowSense to dramatically reduce Firestore read operations while maintaining real-time data updates.

**Problem:** The original system was hitting Firebase Spark plan limits (50,000 reads/day) with just 3 devices and the dashboard open for a few hours.

**Solution:** Multi-tier caching system that reduces Firestore reads by ~95-97% while preserving real-time functionality.

---

## Architecture Components

### 1. Frontend Cache (Browser Memory)
**Location:** `app/static/main.js` - `dataCache` object

**Purpose:** Store all loaded readings in browser memory and only fetch new data on refresh.

**How It Works:**
```javascript
// Structure
dataCache = {
    readings: [/* all readings loaded so far */],
    last_fetch_timestamp: "2024-11-29T10:30:00Z"
}

// First page load
User opens page → Fetch 800 readings (200 per device × 4 devices)
                → Store in dataCache
                → Display charts and table
                → Set last_fetch_timestamp

// Auto-refresh (60 seconds later)
Timer triggers → Fetch only readings AFTER last_fetch_timestamp
              → Merge new readings with cached readings
              → Update charts and table
              → Update last_fetch_timestamp
```

**Benefits:**
- **First load:** 803 Firestore reads (800 readings + 3 device metadata)
- **Subsequent refreshes:** ~6 Firestore reads (3 device metadata + ~3 new readings)
- **Savings:** 803 → 6 per refresh (99.2% reduction)

**Cache Lifetime:**
- Lives in browser memory only (not localStorage)
- Lost on page reload
- Maximum 1000 readings retained to prevent memory bloat

---

### 2. Server-Side Cache (Flask Server Memory)
**Location:** `app/cache.py` - `ReadingsCache` class

**Purpose:** Cache recent readings in server RAM to avoid Firestore reads even on first page load.

**How It Works:**
```python
# Structure
_cache = {
    "user_abc123": {
        "device_A": [reading1, reading2, ...],  # Last 200 readings
        "device_B": [reading1, reading2, ...],
        "device_C": [reading1, reading2, ...]
    }
}

_metadata = {
    "user_abc123": {
        "devices": [device_A, device_B, device_C],
        "cached_at": datetime(2024, 11, 29, 10, 30),
        "ttl_expires": datetime(2024, 11, 29, 10, 35)  # 5 min TTL
    }
}

# Device uploads data (every 30 seconds)
ESP32 → Backend /upload_data
      → Write to Firestore (1 write)
      → Update server cache (0 reads)

# User requests data
User → Backend /user_data
     → Check server cache first
     → If cache hit → Return cached data (0 Firestore reads!)
     → If cache miss → Read from Firestore → Populate cache → Return
```

**Benefits:**
- Cache is populated incrementally as devices upload data
- All users benefit from the same cache (important for shared account)
- Cache stays fresh automatically (updated on every device upload)
- TTL of 5 minutes ensures cache doesn't grow stale

**Cache Invalidation:**
- Automatic TTL expiration after 5 minutes
- Manual invalidation on full refresh
- Per-device limit of 200 readings to prevent memory bloat

---

### 3. Incremental Fetching
**Location:** Backend `get_user_device_readings_since()` function

**Purpose:** Only fetch readings newer than a given timestamp.

**How It Works:**
```python
# Frontend sends: ?since=2024-11-29T10:30:00Z
# Backend filters Firestore query:

query = readings_ref.where('server_timestamp', '>', since_timestamp)
                   .order_by('server_timestamp', 'DESCENDING')
                   .limit(100)

# Only new readings are returned
```

**Benefits:**
- Eliminates re-fetching of old readings
- Works with both frontend and server caches
- Firestore only charges for documents returned, not scanned

---

## Data Flow Diagrams

### Device Upload Flow
```
ESP32 Device
    ↓
    | POST /upload_data
    ↓
Backend Routes
    ↓
    ├─→ Write to Firestore: /users/{userId}/devices/{deviceId}/readings/{readingId}
    |   (1 Firestore write)
    |
    └─→ Update Server Cache: cache.update_reading(user_id, device_id, reading)
        (0 Firestore reads)
```

**Firestore Impact per Upload:**
- Writes: 2 (1 reading + 1 last_seen update, throttled to once per minute)
- Reads: 0-1 (cache hit = 0, cache miss for device config = 1)

---

### Dashboard Refresh Flow (With Cache)

```
User Browser
    ↓
    | GET /user_data?since=2024-11-29T10:30:00Z
    ↓
Backend Routes
    ↓
    ├─→ Check Server Cache
    |   Cache Hit? (Fresh data from device uploads)
    |       ↓ YES
    |       └─→ Return cached data (0 Firestore reads!)
    |
    └─→ Cache Miss?
        ↓ YES (cache expired or first load after restart)
        ├─→ Firestore: Query readings since timestamp
        |   (Only new readings: typically 3-10 documents)
        |
        └─→ Populate Server Cache
            └─→ Return data
```

**Firestore Impact per Refresh:**
- **Cache hit:** 0 reads
- **Cache miss (incremental):** 3-10 reads (new readings only)
- **Cache miss (full refresh after TTL):** 803 reads

---

## Firestore Usage Calculations

### Scenario 1: 4 Devices Active, Dashboard Open 24/7

**Device Configuration:**
- 4 devices uploading every 30 seconds
- Dashboard auto-refresh every 60 seconds
- Dashboard left open for 24 hours

#### Device Uploads (24 hours)
```
Uploads per device: 24 hours × 60 min × 2 uploads/min = 2,880 uploads/day
Total uploads: 2,880 × 4 devices = 11,520 uploads/day

Firestore operations per upload:
- Writes: 2 (reading + last_seen, but last_seen throttled to 1/min)
- Reads: 0 (API key cached, device config cached)

Daily writes: 11,520 readings + (1,440 last_seen × 4 devices) = 17,280 writes/day
Daily reads from uploads: ~100 reads/day (cache misses)
```

#### Dashboard Refreshes (24 hours)
```
Refreshes per day: 24 hours × 60 refreshes/hour = 1,440 refreshes/day

With caching:
- First load: 803 reads (800 readings + 3 devices)
- Next 1,439 refreshes within 5 min windows: ~6 reads each
  (3 device metadata + 3 new readings via incremental fetch)

Daily reads from dashboard: 803 + (1,439 × 6) = 9,437 reads/day
```

#### Total Daily Usage
```
Writes: 17,280/day (well under Spark limit of 20,000/day)
Reads: 9,537/day (well under Spark limit of 50,000/day)

✅ SAFE: 81% under read limit
```

---

### Scenario 2: 4 Devices Active, Dashboard NOT Open

**Device Configuration:**
- 4 devices uploading every 30 seconds
- Dashboard closed (no user requests)

#### Daily Firestore Usage
```
Uploads: 11,520/day
Writes: 17,280/day
Reads: ~100/day (only from cache misses during upload)

✅ EXTREMELY SAFE: Devices can run indefinitely without hitting limits
```

**Key Insight:** Device uploads alone are NOT the problem. They use minimal reads and moderate writes. The dashboard refreshes were the read bottleneck.

---

### Scenario 3: Maximum Safe Dashboard Usage

**Question:** How long can the dashboard be open per day with 4 active devices?

**Calculation:**
```
Available daily reads: 50,000
Device upload reads: ~100
Remaining for dashboard: 49,900

First page load: 803 reads
Remaining budget: 49,900 - 803 = 49,097 reads

Reads per refresh (with cache): ~6 reads
Max refreshes: 49,097 / 6 ≈ 8,183 refreshes

At 60-second intervals: 8,183 / 60 = 136 hours = 5.6 days

✅ Dashboard can be open 24/7 for 5+ days before hitting limits
```

**Even safer:** If server cache is fresh (within 5 min TTL):
- Reads per refresh: 0 (pure cache hit)
- Dashboard can be open indefinitely with zero Firestore reads

---

## Cache Configuration

### Tunable Parameters

#### Frontend (app/static/main.js)
```javascript
CONFIG.autoRefreshInterval = 60000;  // Auto-refresh frequency (ms)
const TABLE_INCREMENT = 20;           // Rows to show per "Load More"
const MAX_CACHE_SIZE = 1000;          // Max readings in browser memory
```

#### Server Cache (app/cache.py)
```python
ttl_seconds = 300                      # Cache lifetime (5 minutes)
max_readings_per_device = 200          # Max readings cached per device
```

#### Backend Limits (app/routes.py)
```python
limit = min(limit, 1000)               # Max readings per request
CACHE_DURATION_SECONDS = 300           # API key cache duration
```

---

## Performance Comparison

### Before Caching (Original System)
```
First page load: 206 Firestore reads
Each auto-refresh (60s): 206 Firestore reads
Dashboard open 2.5 hours: 300 refreshes × 206 = 61,800 reads

❌ EXCEEDED LIMIT: Hit 50,000 read cap in ~2.5 hours
```

### After Caching (Current System)
```
First page load: 803 Firestore reads (higher, but we fetch more data)
Each auto-refresh (60s): ~6 Firestore reads (incremental fetch)
Dashboard open 24 hours: 1 + (1,439 × 6) = 9,437 reads

✅ WITHIN LIMITS: Can run 5+ days continuously
✅ 95.5% reduction in refresh reads (206 → 6)
```

---

## Monitoring Cache Effectiveness

### Check Cache Statistics
```python
# In routes.py, add a debug endpoint:
@bp.route('/cache/stats', methods=['GET'])
def cache_stats():
    from app.cache import readings_cache
    return jsonify(readings_cache.get_stats())
```

**Response:**
```json
{
  "cached_users": 1,
  "total_readings": 800,
  "ttl_seconds": 300,
  "max_readings_per_device": 200
}
```

### Monitor Firestore Console
1. Go to Firebase Console → Firestore → Usage
2. Check "Read operations" graph
3. Should see:
   - Spikes when cache expires (every 5 min)
   - Flat lines between spikes (cache hits)
   - ~9,000-10,000 reads/day with 24/7 dashboard

---

## Best Practices

### For Development
1. **Test cache expiration:** Wait 6+ minutes between requests to trigger cache refresh
2. **Monitor cache hits:** Check console logs for "cache hit" vs "cache miss" messages
3. **Clear caches:** Restart server to clear server cache, reload page to clear frontend cache

### For Production
1. **Keep auto-refresh at 60s:** Good balance of real-time updates and efficiency
2. **Monitor daily reads:** Stay well under 40,000 reads/day to leave buffer
3. **Consider upgrade:** If approaching limits with multiple shared users, upgrade to Blaze plan

### For Multiple Users (Shared Account)
1. **Server cache is shared:** All users benefit from the same cached data
2. **Each user has own frontend cache:** Each browser instance maintains separate cache
3. **Coordinated refreshes:** If 3 users have dashboard open with 60s refresh:
   - Server cache serves all 3 (0 Firestore reads if cache fresh)
   - Firestore only queried when cache expires (every 5 min)

---

## Troubleshooting

### Problem: Dashboard shows stale data
**Cause:** Server cache hasn't been updated with new device uploads  
**Solution:** Wait 30-60 seconds for next device upload, or manually refresh with "Refresh Data" button

### Problem: "Load More" button doesn't work
**Cause:** No cached readings or frontend cache exhausted  
**Solution:** Check browser console for errors, verify backend /user_data endpoint accepts `offset` parameter

### Problem: Still hitting read limits
**Cause:** Multiple users refreshing frequently, or cache not working  
**Solution:**
1. Check cache statistics endpoint
2. Verify TTL is set appropriately (300s)
3. Check Firestore console for read patterns
4. Consider increasing auto-refresh interval to 120s or 300s

---

## Summary

The GrowSense caching system uses a **three-tier approach**:

1. **Frontend cache:** Eliminates redundant fetches of old data
2. **Server cache:** Serves recent data without Firestore queries
3. **Incremental fetching:** Only queries new readings when cache expires

**Result:**
- Dashboard can run 24/7 for 5+ days on Spark plan
- Devices can upload indefinitely without hitting limits
- Real-time updates preserved (60-second refresh)
- ~95% reduction in Firestore reads

**Key Metric:** From 61,800 reads per 2.5 hours → 9,437 reads per 24 hours

This architecture scales well and leaves headroom for growth while staying on the free tier.

