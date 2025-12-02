// ========================================
// GrowSense Dashboard JavaScript
// User-centric multi-device dashboard
// ========================================

// Configuration
const CONFIG = {
    apiBaseUrl: window.location.origin,
    autoRefreshInterval: 60000, // 60 seconds
    chartMaxPoints: 120, // Max points on any chart
    maxDevices: 4, // Maximum devices to display
    recentReadingsLimit: 120, // High-res readings to keep (1 hour at 30s intervals)
    historicalHours: 168, // Hours of historical data to fetch (1 week)
    historicalEmptyFetchCooldownMs: 60 * 60 * 1000, // 1 hour cooldown if fetch returns 0 results
};

// localStorage cache key prefix
const CACHE_KEY_PREFIX = 'growsense_cache_';

// Global state
let firebaseAuth = null;
let currentUser = null;
let idToken = null;
let deviceCharts = {}; // Object to store charts: {deviceId: chart}
let deviceTimeRanges = {}; // Object to store selected time range per device: {deviceId: milliseconds}
let autoRefreshTimer = null;
let userDevices = [];
let userData = null;
let userAdvice = null;

// Data cache for incremental fetching (in-memory)
let dataCache = {
    readings: [],           // Recent high-res readings
    hourly_samples: [],     // Sparse historical samples (1 per hour)
    last_fetch_timestamp: null
};

// Flag to prevent multiple historical fetches
let historicalFetchInProgress = false;
let historicalFetchCompleted = false;

// ========================================
// localStorage Cache Functions
// ========================================

function getLocalStorageKey(userId) {
    return `${CACHE_KEY_PREFIX}${userId}`;
}

function loadFromLocalStorage(userId) {
    if (!userId) return null;
    try {
        const key = getLocalStorageKey(userId);
        const cached = localStorage.getItem(key);
        if (cached) {
            const data = JSON.parse(cached);
            // Verify the cache belongs to this user (extra safety)
            if (data.user_id === userId) {
                console.log(`Loaded cache for user ${userId}: ${data.readings?.length || 0} recent, ${data.hourly_samples?.length || 0} hourly`);
                return data;
            }
        }
    } catch (e) {
        console.error('Error loading from localStorage:', e);
    }
    return null;
}

function saveToLocalStorage(userId, cacheData, historicalFetchAttempted = false) {
    if (!userId) return;
    try {
        const key = getLocalStorageKey(userId);
        const existing = loadFromLocalStorage(userId);
        const toSave = {
            user_id: userId,
            cached_at: new Date().toISOString(),
            readings: cacheData.readings || [],
            hourly_samples: cacheData.hourly_samples || [],
            last_fetch_timestamp: cacheData.last_fetch_timestamp,
            // Track when we last attempted historical fetch (for empty result cooldown)
            historical_fetch_attempted_at: historicalFetchAttempted 
                ? new Date().toISOString() 
                : (existing?.historical_fetch_attempted_at || null)
        };
        localStorage.setItem(key, JSON.stringify(toSave));
        console.log(`Saved cache for user ${userId}: ${toSave.readings.length} recent, ${toSave.hourly_samples.length} hourly`);
    } catch (e) {
        console.error('Error saving to localStorage:', e);
        // If storage is full, try clearing old caches
        if (e.name === 'QuotaExceededError') {
            clearOldCaches(userId);
        }
    }
}

function clearLocalStorageCache(userId) {
    if (!userId) return;
    try {
        const key = getLocalStorageKey(userId);
        localStorage.removeItem(key);
        console.log(`Cleared cache for user ${userId}`);
    } catch (e) {
        console.error('Error clearing localStorage:', e);
    }
}

function clearOldCaches(keepUserId) {
    // Clear caches for other users to free up space
    try {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(CACHE_KEY_PREFIX) && key !== getLocalStorageKey(keepUserId)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log(`Cleared ${keysToRemove.length} old cache entries`);
    } catch (e) {
        console.error('Error clearing old caches:', e);
    }
}

// Table display state
let tableDisplayLimit = 20; // How many readings currently shown in table
const TABLE_INCREMENT = 20; // How many more to show when "Load More" clicked

// ========================================
// Firebase Auth Initialization
// ========================================

function initializeFirebase() {
    if (!FIREBASE_CONFIG || !FIREBASE_CONFIG.apiKey) {
        console.error('Firebase config not found. Please set FIREBASE_WEB_CONFIG environment variable.');
        console.error('Current FIREBASE_CONFIG:', FIREBASE_CONFIG);
        showLoginError('Firebase configuration missing. Please set FIREBASE_WEB_CONFIG environment variable. See FIREBASE_WEB_CONFIG_SETUP.md for instructions.');
        return;
    }

    try {
        firebase.initializeApp(FIREBASE_CONFIG);
        firebaseAuth = firebase.auth();
        
        // Listen for auth state changes
        firebaseAuth.onAuthStateChanged((user) => {
            if (user) {
                handleAuthSuccess(user);
            } else {
                handleAuthLogout();
            }
        });
        
        console.log('Firebase initialized');
    } catch (error) {
        console.error('Firebase initialization error:', error);
        showLoginError('Failed to initialize authentication.');
    }
}

// ========================================
// Authentication Functions
// ========================================

async function handleAuthSuccess(user) {
    // IMPORTANT: Reset historical fetch flags when user changes
    // This handles both fresh login AND user switching
    if (!currentUser || currentUser.uid !== user.uid) {
        console.log('[Auth] New user detected, resetting historical fetch flags');
        historicalFetchCompleted = false;
        historicalFetchInProgress = false;
        // Also clear in-memory cache for new user
        dataCache = {
            readings: [],
            hourly_samples: [],
            last_fetch_timestamp: null
        };
    }
    
    currentUser = user;
    try {
        idToken = await user.getIdToken();
        console.log('User authenticated:', user.email);
        
        // Hide login modal, show dashboard
        document.getElementById('login-modal').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';
        
        // Update user email in header
        document.getElementById('user-email').textContent = user.email || 'User';
        
        // Load user data
        await loadUserData();
        
        // Start auto-refresh based on dropdown value
        const refreshInterval = parseInt(document.getElementById('auto-refresh-interval').value);
        if (refreshInterval > 0) {
            CONFIG.autoRefreshInterval = refreshInterval;
            startAutoRefresh();
        }
    } catch (error) {
        console.error('Error getting ID token:', error);
        showLoginError('Failed to get authentication token.');
    }
}

function handleAuthLogout() {
    // Clear localStorage cache for the logging out user
    if (currentUser?.uid) {
        clearLocalStorageCache(currentUser.uid);
    }
    
    currentUser = null;
    idToken = null;
    userDevices = [];
    userData = null;
    userAdvice = null;
    
    // Clear in-memory cache and reset flags
    dataCache = {
        readings: [],
        hourly_samples: [],
        last_fetch_timestamp: null
    };
    historicalFetchInProgress = false;
    historicalFetchCompleted = false;
    
    // Clear all charts
    Object.values(deviceCharts).forEach(charts => {
        if (charts.primary) charts.primary.destroy();
        if (charts.secondary) charts.secondary.destroy();
    });
    deviceCharts = {};
    
    // Show login modal, hide dashboard
    document.getElementById('login-modal').style.display = 'flex';
    document.getElementById('dashboard').style.display = 'none';
    
    // Clear displays
    clearAllDisplays();
}

async function signInWithGoogle() {
    if (!firebaseAuth) {
        showLoginError('Firebase not initialized');
        return;
    }
    
    const provider = new firebase.auth.GoogleAuthProvider();
    try {
        hideLoginError();
        await firebaseAuth.signInWithPopup(provider);
    } catch (error) {
        console.error('Sign-in error:', error);
        showLoginError(error.message || 'Failed to sign in. Please try again.');
    }
}

async function signOut() {
    try {
        await firebaseAuth.signOut();
    } catch (error) {
        console.error('Sign-out error:', error);
    }
}

function showLoginError(message) {
    const errorEl = document.getElementById('login-error');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

function hideLoginError() {
    document.getElementById('login-error').style.display = 'none';
}

// ========================================
// Data Fetching Functions
// ========================================

async function getAuthHeaders() {
    if (!idToken) {
        // Refresh token if needed
        if (currentUser) {
            idToken = await currentUser.getIdToken();
        } else {
            throw new Error('Not authenticated');
        }
    }
    return {
        'Authorization': `Bearer ${idToken}`,
        'Content-Type': 'application/json'
    };
}

async function fetchUserDevices() {
    try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${CONFIG.apiBaseUrl}/devices`, {
            headers: headers
        });
        
        if (response.status === 401) {
            // Token expired, try to refresh
            if (currentUser) {
                idToken = await currentUser.getIdToken(true);
                return fetchUserDevices(); // Retry
            }
            throw new Error('Authentication required');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        return data.devices || [];
    } catch (error) {
        console.error('Error fetching devices:', error);
        throw error;
    }
}

async function fetchUserData() {
    try {
        const headers = await getAuthHeaders();
        
        // Build URL with optional incremental fetch parameter
        // Limit to 120 readings per device (1 hour at 30s intervals)
        let url = `${CONFIG.apiBaseUrl}/user_data?limit=${CONFIG.recentReadingsLimit * CONFIG.maxDevices}`;
        
        // If we have cached data with a timestamp, do incremental fetch
        if (dataCache.last_fetch_timestamp) {
            url += `&since=${encodeURIComponent(dataCache.last_fetch_timestamp)}`;
            console.log(`Fetching incremental data since ${dataCache.last_fetch_timestamp}`);
        }
        
        const response = await fetch(url, { headers: headers });
        
        if (response.status === 401) {
            if (currentUser) {
                idToken = await currentUser.getIdToken(true);
                return fetchUserData(); // Retry
            }
            throw new Error('Authentication required');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Handle incremental fetch: merge new data with cache
        if (dataCache.last_fetch_timestamp && dataCache.readings.length > 0) {
            console.log(`Merging ${data.readings?.length || 0} new readings with ${dataCache.readings.length} cached readings`);
            
            // Merge new readings with cached readings
            const mergedReadings = mergeReadings(dataCache.readings, data.readings || []);
            
            // Update data with merged readings
            data.readings = mergedReadings;
            data.total_readings = mergedReadings.length;
            
            // Update cache
            dataCache.readings = mergedReadings;
        } else {
            // First load or cache was empty
            console.log(`Initial data load: ${data.readings?.length || 0} readings`);
            dataCache.readings = data.readings || [];
        }
        
        // Update last fetch timestamp for next incremental fetch
        dataCache.last_fetch_timestamp = new Date().toISOString();
        
        return data;
    } catch (error) {
        console.error('Error fetching user data:', error);
        throw error;
    }
}

async function fetchHistoricalData() {
    /**
     * Fetch sparse historical readings (one per hour) for week/all-time views.
     * This data is cached in localStorage and only fetched once.
     * 
     * WARNING: This is expensive (~1000 Firestore reads)! Should only be called ONCE per user.
     */
    try {
        const headers = await getAuthHeaders();
        const url = `${CONFIG.apiBaseUrl}/user_data/historical?hours=${CONFIG.historicalHours}`;
        
        console.warn(`⚠️ [EXPENSIVE] Fetching historical data - THIS SHOULD ONLY HAPPEN ONCE PER USER!`);
        console.log(`Fetching historical data for past ${CONFIG.historicalHours} hours...`);
        
        const response = await fetch(url, { headers: headers });
        
        if (response.status === 401) {
            if (currentUser) {
                idToken = await currentUser.getIdToken(true);
                return fetchHistoricalData(); // Retry
            }
            throw new Error('Authentication required');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`Fetched ${data.total_readings || 0} historical hourly samples`);
        
        return data.readings || [];
    } catch (error) {
        console.error('Error fetching historical data:', error);
        throw error;
    }
}

function mergeReadings(oldReadings, newReadings) {
    if (!newReadings || newReadings.length === 0) {
        return oldReadings;
    }
    
    // Create a map of existing readings by ID to avoid duplicates
    const readingMap = new Map();
    
    // Add old readings to map
    oldReadings.forEach(reading => {
        if (reading.id) {
            readingMap.set(reading.id, reading);
        }
    });
    
    // Add new readings (will overwrite if ID exists)
    newReadings.forEach(reading => {
        if (reading.id) {
            readingMap.set(reading.id, reading);
        }
    });
    
    // Convert back to array and sort by timestamp (newest first)
    const merged = Array.from(readingMap.values());
    merged.sort((a, b) => {
        const timeA = new Date(a.server_timestamp || a.timestamp);
        const timeB = new Date(b.server_timestamp || b.timestamp);
        return timeB - timeA; // Descending order (newest first)
    });
    
    // Keep only most recent readings to prevent memory bloat
    // 120 per device × 4 devices = 480 max recent readings
    const maxReadings = CONFIG.recentReadingsLimit * CONFIG.maxDevices;
    return merged.slice(0, maxReadings);
}

async function fetchUserAdvice() {
    try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${CONFIG.apiBaseUrl}/user_advice`, {
            headers: headers
        });
        
        if (response.status === 401) {
            if (currentUser) {
                idToken = await currentUser.getIdToken(true);
                return fetchUserAdvice(); // Retry
            }
            throw new Error('Authentication required');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        return data.advice || null;
    } catch (error) {
        console.error('Error fetching advice:', error);
        throw error;
    }
}

// ========================================
// Main Data Loading
// ========================================

async function loadUserData() {
    updateStatus('Loading data...', 'loading');
    
    try {
        const userId = currentUser?.uid;
        if (!userId) {
            throw new Error('Not authenticated');
        }
        
        // Check localStorage for existing cache FOR THIS USER
        const cachedData = loadFromLocalStorage(userId);
        
        // IMPORTANT: Only fetch historical if we truly don't have it cached
        // Check both localStorage AND in-memory cache, AND the fetch completed flag
        const hasHistoricalInLocalStorage = cachedData?.hourly_samples?.length > 0;
        const hasHistoricalInMemory = dataCache.hourly_samples?.length > 0;
        
        // For users with no data: check if we recently tried to fetch (cooldown period)
        // This prevents spamming fetches for accounts with no data
        let recentlyFetchedEmpty = false;
        if (cachedData?.historical_fetch_attempted_at) {
            const lastAttempt = new Date(cachedData.historical_fetch_attempted_at).getTime();
            const cooldownExpired = (Date.now() - lastAttempt) > CONFIG.historicalEmptyFetchCooldownMs;
            recentlyFetchedEmpty = !cooldownExpired;
            if (recentlyFetchedEmpty) {
                const minutesRemaining = Math.round((CONFIG.historicalEmptyFetchCooldownMs - (Date.now() - lastAttempt)) / 60000);
                console.log(`[Cache Check] Empty fetch cooldown active (${minutesRemaining} min remaining)`);
            }
        }
        
        // Need to fetch if: no data in cache AND we haven't completed a fetch for this session AND not in cooldown
        let needsHistoricalFetch = !hasHistoricalInLocalStorage && !hasHistoricalInMemory && !historicalFetchCompleted && !recentlyFetchedEmpty;
        
        console.log(`[Cache Check] localStorage: ${hasHistoricalInLocalStorage ? cachedData.hourly_samples.length + ' samples' : 'empty'}, memory: ${hasHistoricalInMemory ? dataCache.hourly_samples.length + ' samples' : 'empty'}, fetchCompleted: ${historicalFetchCompleted}, cooldown: ${recentlyFetchedEmpty}, needsFetch: ${needsHistoricalFetch}`);
        
        // Restore cache from localStorage if available (and not already in memory)
        if (cachedData && !hasHistoricalInMemory) {
            dataCache.readings = cachedData.readings || [];
            dataCache.hourly_samples = cachedData.hourly_samples || [];
            dataCache.last_fetch_timestamp = cachedData.last_fetch_timestamp;
            // Mark historical as complete since we loaded it from localStorage
            if (cachedData.hourly_samples?.length > 0) {
                historicalFetchCompleted = true;
            }
            console.log('[Cache] Restored from localStorage');
        }
        
        // Fetch devices and recent data
        const [devices, data] = await Promise.all([
            fetchUserDevices(),
            fetchUserData()
        ]);
        
        userDevices = devices.slice(0, CONFIG.maxDevices); // Limit to 4 devices
        userData = data;
        
        // Fetch historical data ONLY if needed (one-time per user)
        let historicalFetchJustAttempted = false;
        if (needsHistoricalFetch) {
            if (historicalFetchInProgress) {
                console.log('[Historical] Fetch already in progress, waiting...');
            } else {
                historicalFetchInProgress = true;
                historicalFetchJustAttempted = true;
                console.log('[Historical] Fetching historical data (this should only happen ONCE per user)...');
                try {
                    const historicalReadings = await fetchHistoricalData();
                    dataCache.hourly_samples = historicalReadings;
                    console.log(`[Historical] Loaded ${historicalReadings.length} hourly samples`);
                } catch (histError) {
                    console.error('[Historical] Error:', histError);
                    // Continue without historical data
                    dataCache.hourly_samples = [];
                } finally {
                    historicalFetchInProgress = false;
                    historicalFetchCompleted = true; // Mark complete even if 0 results
                }
            }
        } else {
            console.log(`[Historical] Using cached data (${dataCache.hourly_samples?.length || 0} samples)`);
        }
        
        // Save updated cache to localStorage
        // Pass true if we just attempted a historical fetch (for cooldown tracking)
        saveToLocalStorage(userId, dataCache, historicalFetchJustAttempted);
        
        // Reset table display limit only on initial load, not refreshes
        if (!cachedData) {
            tableDisplayLimit = 20;
        }
        
        // Update displays
        updateDeviceCards();
        updateUnifiedTable();
        
        const totalReadings = (data.total_readings || 0) + (dataCache.hourly_samples?.length || 0);
        updateStatus(`✓ Loaded ${data.total_readings || 0} recent + ${dataCache.hourly_samples?.length || 0} historical`, 'success');
        updateDataCount(data.total_readings || 0);
        updateLastUpdated();
        
    } catch (error) {
        console.error('Error loading user data:', error);
        updateStatus(`Error: ${error.message}`, 'error');
        if (error.message.includes('Authentication')) {
            // Redirect to login
            signOut();
        }
    }
}

async function loadUserAdvice() {
    const adviceBtn = document.getElementById('get-advice-btn');
    const originalText = adviceBtn.textContent;
    adviceBtn.disabled = true;
    adviceBtn.textContent = 'Loading...';
    
    try {
        const advice = await fetchUserAdvice();
        
        // Validate advice structure
        if (!advice || typeof advice !== 'object') {
            throw new Error('Invalid advice format received');
        }
        
        // Ensure it has the expected structure
        if (!advice.overall_advice && !advice.device_advice && !advice.insights) {
            console.warn('Unexpected advice structure:', advice);
            // Try to extract if it's nested
            if (advice.advice) {
                userAdvice = advice.advice;
            } else {
                throw new Error('Advice does not contain expected fields');
            }
        } else {
            userAdvice = advice;
        }
        
        updateAdviceDisplay();
    } catch (error) {
        console.error('Error loading advice:', error);
        updateStatus(`Error loading advice: ${error.message}`, 'error');
        // Clear advice display on error
        document.getElementById('general-advice').innerHTML = '<p class="error">Failed to load advice. Please try again.</p>';
        document.getElementById('insights-list').innerHTML = '';
    } finally {
        adviceBtn.disabled = false;
        adviceBtn.textContent = originalText;
    }
}

// ========================================
// Display Updates - Device Cards
// ========================================

function updateDeviceCards() {
    const grid = document.getElementById('devices-grid');
    grid.innerHTML = '';
    
    if (userDevices.length === 0) {
        grid.innerHTML = '<div class="no-devices-message">No devices registered. Register a device to start monitoring.</div>';
        return;
    }
    
    // Create cards for up to 4 devices
    for (let i = 0; i < Math.min(userDevices.length, CONFIG.maxDevices); i++) {
        const device = userDevices[i];
        const deviceId = device.device_id;
        
        // Get readings for this device
        const deviceReadings = (userData.readings || []).filter(r => r.device_id === deviceId);
        const latestReading = deviceReadings[0] || null;
        
        // Create device card
        const card = createDeviceCard(device, latestReading, deviceReadings);
        grid.appendChild(card);
        
        // Initialize chart for this device
        if (deviceReadings.length > 0) {
            initializeDeviceChart(deviceId, deviceReadings);
        }
    }
    
    // Update device-specific advice
    updateDeviceSpecificAdvice();
}

function createDeviceCard(device, latestReading, readings) {
    const card = document.createElement('div');
    card.className = 'device-card';
    card.id = `device-card-${device.device_id}`;
    
    // Status indicator (online if last_seen is recent)
    const lastSeen = device.last_seen ? new Date(device.last_seen) : null;
    const isOnline = lastSeen && (Date.now() - lastSeen.getTime()) < 3600000; // 1 hour
    const statusClass = isOnline ? 'status-online' : 'status-offline';
    const statusText = isOnline ? '● Online' : '○ Offline';
    
    // Preserve existing time range for this device (don't reset on refresh)
    const existingTimeRange = deviceTimeRanges[device.device_id];
    // Only initialize to null if truly not set (undefined)
    if (existingTimeRange === undefined) {
        deviceTimeRanges[device.device_id] = null; // null = all time
    }
    
    // Determine current sampling rate selection
    // Default to 30s if not known, or use stored value if we have it in device metadata
    const currentInterval = device.target_interval || 30;
    
    // Extract UV light from raw_json if available
    let uvLight = null;
    if (latestReading?.raw_json?.uv_light !== undefined) {
        uvLight = latestReading.raw_json.uv_light;
    } else if (latestReading?.uv_light !== undefined) {
        uvLight = latestReading.uv_light;
    }
    
    card.innerHTML = `
        <div class="device-card-header">
            <h3>${device.name || device.device_id}</h3>
            <span class="device-status ${statusClass}">${statusText}</span>
        </div>
        <div class="device-readings">
            <div class="device-reading">
                <span class="reading-icon">🌡️</span>
                <span class="reading-value">${latestReading?.temperature?.toFixed(1) || '--'}</span>
                <span class="reading-unit">°C</span>
            </div>
            <div class="device-reading">
                <span class="reading-icon">💧</span>
                <span class="reading-value">${latestReading?.humidity?.toFixed(1) || '--'}</span>
                <span class="reading-unit">%</span>
            </div>
            <div class="device-reading device-reading-split">
                <div class="device-reading-half">
                    <span class="reading-icon">☀️</span>
                    <span class="reading-value">${latestReading?.light ? Math.round(latestReading.light) : '--'}</span>
                    <span class="reading-unit">lux</span>
                </div>
                <div class="device-reading-half">
                    <span class="reading-value">${uvLight !== null ? uvLight.toFixed(1) : '--'}</span>
                    <span class="reading-unit">UV</span>
                </div>
            </div>
            <div class="device-reading">
                <span class="reading-icon">🌿</span>
                <span class="reading-value">${latestReading?.soil_moisture?.toFixed(1) || '--'}</span>
                <span class="reading-unit">%</span>
            </div>
        </div>
        <div class="chart-controls">
            <div class="control-group">
                <label for="time-range-${device.device_id}">Time Range:</label>
                <select id="time-range-${device.device_id}" class="time-range-select" data-device-id="${device.device_id}">
                    <option value="3600000" ${deviceTimeRanges[device.device_id] === 3600000 ? 'selected' : ''}>1 hour</option>
                    <option value="86400000" ${deviceTimeRanges[device.device_id] === 86400000 ? 'selected' : ''}>1 day</option>
                    <option value="604800000" ${deviceTimeRanges[device.device_id] === 604800000 ? 'selected' : ''}>1 week</option>
                    <option value="null" ${deviceTimeRanges[device.device_id] === null || deviceTimeRanges[device.device_id] === undefined ? 'selected' : ''}>All time</option>
                </select>
            </div>
            <div class="control-group">
                <label for="sampling-rate-${device.device_id}">Sampling:</label>
                <select id="sampling-rate-${device.device_id}" class="sampling-rate-select" data-device-id="${device.device_id}">
                    <option value="15" ${currentInterval == 15 ? 'selected' : ''}>15s</option>
                    <option value="30" ${currentInterval == 30 ? 'selected' : ''}>30s</option>
                    <option value="60" ${currentInterval == 60 ? 'selected' : ''}>1m</option>
                    <option value="900" ${currentInterval == 900 ? 'selected' : ''}>15m</option>
                    <option value="1800" ${currentInterval == 1800 ? 'selected' : ''}>30m</option>
                </select>
            </div>
        </div>
        <div id="no-data-message-${device.device_id}" class="no-data-message" style="display: none;"></div>
        <div class="device-chart-container">
            <canvas id="chart-primary-${device.device_id}"></canvas>
        </div>
        <div class="device-chart-container">
            <canvas id="chart-secondary-${device.device_id}"></canvas>
        </div>
        <div id="device-advice-${device.device_id}" class="device-advice" style="display: none;"></div>
    `;
    
    return card;
}

// ========================================
// Chart Functions - Individual Device Charts
// ========================================

function downsampleReadings(readings, maxPoints) {
    /**
     * Downsample readings to maxPoints while preserving trends.
     * Uses simple stride-based sampling (every Nth point).
     * For more accurate trends, could use LTTB algorithm.
     */
    if (!readings || readings.length <= maxPoints) {
        return readings;
    }
    
    const stride = Math.ceil(readings.length / maxPoints);
    const sampled = [];
    
    for (let i = 0; i < readings.length; i += stride) {
        sampled.push(readings[i]);
    }
    
    // Always include the last reading for most recent data
    if (sampled[sampled.length - 1] !== readings[readings.length - 1]) {
        sampled.push(readings[readings.length - 1]);
    }
    
    return sampled;
}

function initializeDeviceChart(deviceId, readings) {
    const primaryCanvasId = `chart-primary-${deviceId}`;
    const secondaryCanvasId = `chart-secondary-${deviceId}`;
    const primaryCanvas = document.getElementById(primaryCanvasId);
    const secondaryCanvas = document.getElementById(secondaryCanvasId);
    const noDataMessageEl = document.getElementById(`no-data-message-${deviceId}`);
    
    if (!primaryCanvas || !secondaryCanvas) {
        console.warn(`Canvas not found for device ${deviceId}`);
        return;
    }
    
    // Destroy existing charts if any
    if (deviceCharts[deviceId]) {
        if (deviceCharts[deviceId].primary) deviceCharts[deviceId].primary.destroy();
        if (deviceCharts[deviceId].secondary) deviceCharts[deviceId].secondary.destroy();
    }
    
    // Initialize container if not exists
    deviceCharts[deviceId] = {};
    
    // Get selected time range
    const timeRange = deviceTimeRanges[deviceId];
    let chartReadings = [];
    let timeRangeText = 'all time';
    
    // Select data source based on timeframe
    // 1 hour (3600000ms): Use recent high-res readings
    // 1 day (86400000ms): Use hourly samples
    // 1 week (604800000ms): Use hourly samples
    // All time (null): Use hourly samples (sparse)
    
    if (timeRange === 3600000) {
        // 1 hour view: use recent high-res readings
        timeRangeText = 'the past hour';
        const cutoffTime = Date.now() - timeRange;
        chartReadings = readings.filter(r => {
            const timestamp = new Date(r.timestamp || r.server_timestamp).getTime();
            return timestamp >= cutoffTime;
        });
    } else {
        // Day/Week/All time: use hourly samples from cache
        const hourlyForDevice = (dataCache.hourly_samples || []).filter(r => r.device_id === deviceId);
        
        if (timeRange === 86400000) {
            // 1 day: filter hourly samples to last 24 hours
            timeRangeText = 'the past day';
            const cutoffTime = Date.now() - timeRange;
            chartReadings = hourlyForDevice.filter(r => {
                const timestamp = new Date(r.timestamp || r.server_timestamp).getTime();
                return timestamp >= cutoffTime;
            });
        } else if (timeRange === 604800000) {
            // 1 week: use all hourly samples (up to 168 hours)
            timeRangeText = 'the past week';
            const cutoffTime = Date.now() - timeRange;
            chartReadings = hourlyForDevice.filter(r => {
                const timestamp = new Date(r.timestamp || r.server_timestamp).getTime();
                return timestamp >= cutoffTime;
            });
        } else {
            // All time (null): use all hourly samples, downsample if needed
            timeRangeText = 'all time';
            chartReadings = [...hourlyForDevice];
        }
        
        // If no hourly samples, fall back to recent readings
        if (chartReadings.length === 0) {
            console.log(`No hourly samples for ${deviceId}, using recent readings`);
            chartReadings = [...readings];
        }
    }
    
    // Check if we have any data
    if (chartReadings.length === 0) {
        if (noDataMessageEl) {
            if (readings.length === 0 && (dataCache.hourly_samples || []).length === 0) {
                noDataMessageEl.textContent = 'No data received';
            } else {
                noDataMessageEl.textContent = `No data for ${timeRangeText}`;
            }
            noDataMessageEl.style.display = 'block';
        }
        // Create empty charts
        const ctxP = primaryCanvas.getContext('2d');
        const ctxS = secondaryCanvas.getContext('2d');
        const emptyConfig = {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
        };
        deviceCharts[deviceId].primary = new Chart(ctxP, emptyConfig);
        deviceCharts[deviceId].secondary = new Chart(ctxS, emptyConfig);
        return;
    }
    
    // Hide no data message if we have data
    if (noDataMessageEl) {
        noDataMessageEl.style.display = 'none';
    }
    
    // Sort readings by timestamp (oldest first)
    chartReadings.sort((a, b) => {
        const timeA = new Date(a.timestamp || a.server_timestamp).getTime();
        const timeB = new Date(b.timestamp || b.server_timestamp).getTime();
        return timeA - timeB; // Ascending order (oldest first for chart)
    });
    
    // Downsample to max chartMaxPoints (120)
    const sortedReadings = downsampleReadings(chartReadings, CONFIG.chartMaxPoints);
    const labels = sortedReadings.map(r => r.timestamp || r.server_timestamp);
    
    // ==========================================
    // Top Chart: Temp, Humidity, Soil Moisture
    // ==========================================
    const ctxPrimary = primaryCanvas.getContext('2d');
    deviceCharts[deviceId].primary = new Chart(ctxPrimary, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: sortedReadings.map(r => r.temperature),
                    borderColor: '#4CAF50', // Green
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    yAxisID: 'y',
                    tension: 0.4,
                },
                {
                    label: 'Humidity (%)',
                    data: sortedReadings.map(r => r.humidity),
                    borderColor: '#42A5F5', // Light blue
                    backgroundColor: 'rgba(66, 165, 245, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                },
                {
                    label: 'Soil Moisture (%)',
                    data: sortedReadings.map(r => r.soil_moisture),
                    borderColor: '#1976D2', // Med-dark blue
                    backgroundColor: 'rgba(25, 118, 210, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: { boxWidth: 10, font: { size: 10 }, padding: 10 }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: function(tooltipItems) {
                            if (tooltipItems.length > 0) {
                                return formatChartTimestamp(tooltipItems[0].label);
                            }
                            return '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: false, // Hide X axis labels on top chart
                    grid: { display: false } // Minimal grid for cleaner look
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Temp (°C)', font: { size: 9 } },
                    ticks: { font: { size: 9 } }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Percentage (%)', font: { size: 9 } },
                    grid: { drawOnChartArea: false },
                    ticks: { font: { size: 9 }, max: 100, min: 0 }
                }
            }
        }
    });

    // ==========================================
    // Bottom Chart: Light and UV
    // ==========================================
    const ctxSecondary = secondaryCanvas.getContext('2d');
    deviceCharts[deviceId].secondary = new Chart(ctxSecondary, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Light (lux)',
                    data: sortedReadings.map(r => r.light),
                    borderColor: '#FFC107', // Yellow
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
                    yAxisID: 'y',
                    tension: 0.4,
                },
                {
                    label: 'UV Index',
                    data: sortedReadings.map(r => {
                        if (r.raw_json && r.raw_json.uv_light !== undefined) {
                            return r.raw_json.uv_light;
                        } else if (r.uv_light !== undefined) {
                            return r.uv_light;
                        }
                        return null;
                    }),
                    borderColor: '#9C27B0', // Light purple
                    backgroundColor: 'rgba(156, 39, 176, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: { boxWidth: 10, font: { size: 10 }, padding: 10 }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: function(tooltipItems) {
                            if (tooltipItems.length > 0) {
                                return formatChartTimestamp(tooltipItems[0].label);
                            }
                            return '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        maxTicksLimit: 6,
                        font: { size: 10 },
                        callback: function(value, index, ticks) {
                            const label = this.getLabelForValue(value);
                            return formatChartTimestamp(label);
                        }
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Light (lux)', font: { size: 9 } },
                    ticks: { font: { size: 9 } }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'UV Index', font: { size: 9 } },
                    grid: { drawOnChartArea: false },
                    ticks: { font: { size: 9 } },
                    min: 0,           // Hard minimum: never show negative
                    suggestedMax: 1.0 // Soft max: starts at 1.0, expands if data exceeds
                }
            }
        }
    });
}

// ========================================
// Display Updates - Advice
// ========================================

function updateAdviceDisplay() {
    // Always show the advice section (button is always visible)
    document.getElementById('advice-section').style.display = 'block';
    
    if (!userAdvice) {
        // Clear advice content if no advice yet
        document.getElementById('general-advice').innerHTML = '<p>Click "Get Advice" to receive plant care recommendations based on your sensor data.</p>';
        document.getElementById('insights-list').innerHTML = '';
        return;
    }
    
    // Update general advice
    const generalAdviceEl = document.getElementById('general-advice');
    if (userAdvice.overall_advice) {
        // Escape HTML first
        let escapedAdvice = userAdvice.overall_advice
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Convert markdown-style formatting to HTML
        // Handle **bold** text (non-greedy match)
        escapedAdvice = escapedAdvice.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
        // Handle any remaining single * for emphasis
        escapedAdvice = escapedAdvice.replace(/\*([^*]+?)\*/g, '<em>$1</em>');
        // Remove any remaining standalone ** that weren't matched
        escapedAdvice = escapedAdvice.replace(/\*\*/g, '');
        
        generalAdviceEl.innerHTML = `<p>${escapedAdvice}</p>`;
    } else {
        generalAdviceEl.innerHTML = '<p>No general advice available.</p>';
    }
    
    // Update insights
    const insightsEl = document.getElementById('insights-list');
    if (userAdvice.insights && userAdvice.insights.length > 0) {
        // Filter out default/fallback insights and escape HTML
        const validInsights = userAdvice.insights.filter(insight => {
            const lower = insight.toLowerCase();
            return !lower.includes('sensor data analyzed successfully') && 
                   !lower.includes('review device-specific recommendations');
        });
        
        if (validInsights.length > 0) {
            insightsEl.innerHTML = '<h3>Insights:</h3><ul>' + 
                validInsights.map(insight => {
                    // Escape HTML first
                    let escaped = insight
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    
                    // Convert markdown-style formatting to HTML
                    // Handle **bold** text (non-greedy match)
                    escaped = escaped.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
                    // Handle any remaining single * for emphasis
                    escaped = escaped.replace(/\*([^*]+?)\*/g, '<em>$1</em>');
                    // Remove any remaining standalone ** that weren't matched
                    escaped = escaped.replace(/\*\*/g, '');
                    
                    return `<li>${escaped}</li>`;
                }).join('') + 
                '</ul>';
        } else {
            insightsEl.innerHTML = '';
        }
    } else {
        insightsEl.innerHTML = '';
    }
    
    // Update device-specific advice (will be called separately)
    updateDeviceSpecificAdvice();
}

function updateDeviceSpecificAdvice() {
    if (!userAdvice || !userAdvice.device_advice) {
        return;
    }
    
    userAdvice.device_advice.forEach(deviceAdvice => {
        const adviceEl = document.getElementById(`device-advice-${deviceAdvice.device_id}`);
        if (adviceEl) {
            const priorityClass = `priority-${deviceAdvice.priority || 'low'}`;
            adviceEl.className = `device-advice ${priorityClass}`;
            adviceEl.style.display = 'block';
            
            let html = `<div class="device-advice-content">`;
            html += `<p class="device-advice-text">${deviceAdvice.advice || 'No specific advice for this device.'}</p>`;
            
            if (deviceAdvice.recommendations && deviceAdvice.recommendations.length > 0) {
                html += `<ul class="device-recommendations">`;
                deviceAdvice.recommendations.forEach(rec => {
                    html += `<li>${rec}</li>`;
                });
                html += `</ul>`;
            }
            html += `</div>`;
            
            adviceEl.innerHTML = html;
        }
    });
}

// ========================================
// Display Updates - Unified Table
// ========================================

function updateUnifiedTable() {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    
    if (!userData || !userData.readings || userData.readings.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="no-data">No data available. Click "Refresh Data" to load.</td></tr>';
        updateLoadMoreButton(0, 0);
        return;
    }
    
    const allReadings = userData.readings;
    const totalReadings = allReadings.length;
    
    // Show only the first 'tableDisplayLimit' readings
    const displayedReadings = allReadings.slice(0, tableDisplayLimit);
    
    displayedReadings.forEach(reading => {
        const row = document.createElement('tr');
        
        const deviceName = reading.device_name || reading.device_id || 'Unknown';
        const timestamp = reading.timestamp || reading.server_timestamp;
        const temp = reading.temperature;
        const humidity = reading.humidity;
        const light = reading.light;
        const soil = reading.soil_moisture;
        
        // Extract UV from raw_json if available
        let uvLight = null;
        if (reading.raw_json && reading.raw_json.uv_light !== undefined) {
            uvLight = reading.raw_json.uv_light;
        } else if (reading.uv_light !== undefined) {
            uvLight = reading.uv_light;
        }
        
        row.innerHTML = `
            <td>${deviceName}</td>
            <td>${formatTimestamp(timestamp)}</td>
            <td>${temp !== null && temp !== undefined ? temp.toFixed(1) : '--'}</td>
            <td>${humidity !== null && humidity !== undefined ? humidity.toFixed(1) : '--'}</td>
            <td>${light !== null && light !== undefined ? Math.round(light) : '--'}</td>
            <td>${uvLight !== null && uvLight !== undefined ? uvLight.toFixed(1) : '--'}</td>
            <td>${soil !== null && soil !== undefined ? soil.toFixed(1) : '--'}</td>
        `;
        
        tbody.appendChild(row);
    });
    
    // Update Load More button visibility
    updateLoadMoreButton(displayedReadings.length, totalReadings);
}

function updateLoadMoreButton(displayed, total) {
    const loadMoreContainer = document.getElementById('load-more-container');
    const loadMoreBtn = document.getElementById('load-more-btn');
    const loadMoreText = document.getElementById('load-more-text');
    
    if (!loadMoreContainer || !loadMoreBtn || !loadMoreText) return;
    
    const remaining = total - displayed;
    
    if (remaining > 0) {
        loadMoreContainer.style.display = 'block';
        loadMoreText.textContent = `Showing ${displayed} of ${total} readings`;
        loadMoreBtn.textContent = `Load ${Math.min(TABLE_INCREMENT, remaining)} More`;
    } else {
        loadMoreContainer.style.display = 'none';
    }
}

function loadMoreReadings() {
    if (!userData || !userData.readings) return;
    
    const totalReadings = userData.readings.length;
    const currentlyDisplayed = tableDisplayLimit;
    
    // Check if we've exhausted cached data
    if (currentlyDisplayed >= totalReadings) {
        // Option B: Fetch more from Firestore
        loadMoreFromFirestore();
    } else {
        // Option A: Reveal more from cache
        tableDisplayLimit += TABLE_INCREMENT;
        updateUnifiedTable();
    }
}

async function loadMoreFromFirestore() {
    const loadMoreBtn = document.getElementById('load-more-btn');
    const originalText = loadMoreBtn.textContent;
    loadMoreBtn.disabled = true;
    loadMoreBtn.textContent = 'Loading...';
    
    try {
        // Fetch additional readings with offset
        const currentCount = userData.readings.length;
        const headers = await getAuthHeaders();
        const response = await fetch(`${CONFIG.apiBaseUrl}/user_data?limit=${TABLE_INCREMENT}&offset=${currentCount}`, {
            headers: headers
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.readings && data.readings.length > 0) {
            // Append new readings to userData
            userData.readings = userData.readings.concat(data.readings);
            tableDisplayLimit += data.readings.length;
            updateUnifiedTable();
        } else {
            // No more data available
            const loadMoreContainer = document.getElementById('load-more-container');
            loadMoreContainer.style.display = 'none';
        }
        
    } catch (error) {
        console.error('Error loading more readings:', error);
        updateStatus('Error loading more data', 'error');
    } finally {
        loadMoreBtn.disabled = false;
        loadMoreBtn.textContent = originalText;
    }
}

// ========================================
// Utility Functions
// ========================================

function formatTimestamp(timestamp) {
    if (!timestamp) return '--';
    try {
        const date = new Date(timestamp);
        return date.toLocaleString();
    } catch (e) {
        return timestamp;
    }
}

function formatChartTimestamp(timestamp) {
    if (!timestamp) return '--';
    try {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const oneDayMs = 24 * 60 * 60 * 1000;
        
        // Within last 24 hours: show only time (9:32pm)
        if (diffMs < oneDayMs) {
            return date.toLocaleTimeString('en-US', { 
                hour: 'numeric', 
                minute: '2-digit',
                hour12: true 
            }).toLowerCase();
        }
        
        // Older than 24 hours: show abbreviated month, day, time (Nov 22, 8:43am)
        const month = date.toLocaleDateString('en-US', { month: 'short' });
        const day = date.getDate();
        const time = date.toLocaleTimeString('en-US', { 
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
        }).toLowerCase();
        
        return `${month} ${day}, ${time}`;
    } catch (e) {
        return timestamp;
    }
}

function updateStatus(message, type = 'info') {
    const statusEl = document.getElementById('status-message');
    statusEl.textContent = message;
    
    statusEl.classList.remove('loading', 'success', 'error', 'warning');
    if (type) {
        statusEl.classList.add(type);
    }
}

function updateDataCount(count) {
    document.getElementById('data-count').textContent = `${count} readings`;
}

function updateLastUpdated() {
    const now = new Date().toLocaleTimeString();
    // Removed last-updated element, but keeping function for compatibility
}

function clearAllDisplays() {
    // Clear device grid
    document.getElementById('devices-grid').innerHTML = '';
    
    // Clear charts
    Object.values(deviceCharts).forEach(charts => {
        if (charts.primary) charts.primary.destroy();
        if (charts.secondary) charts.secondary.destroy();
    });
    deviceCharts = {};
    
    // Clear table
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '<tr><td colspan="6" class="no-data">No data available</td></tr>';
    
    // Clear advice
    document.getElementById('advice-section').style.display = 'none';
}

// ========================================
// Auto-Refresh Functions
// ========================================

function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(() => {
        console.log('Auto-refreshing data...');
        loadUserData();
    }, CONFIG.autoRefreshInterval);
    console.log(`Auto-refresh enabled (every ${CONFIG.autoRefreshInterval / 1000}s)`);
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
        console.log('Auto-refresh disabled');
    }
}

// ========================================
// Event Listeners Setup
// ========================================

function setupEventListeners() {
    // Google sign-in button
    document.getElementById('google-signin-btn').addEventListener('click', signInWithGoogle);
    
    // Logout button
    document.getElementById('logout-btn').addEventListener('click', signOut);
    
    // Get advice button
    document.getElementById('get-advice-btn').addEventListener('click', loadUserAdvice);
    
    // Refresh data button
    document.getElementById('refresh-btn').addEventListener('click', loadUserData);
    
    // Load More button
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreReadings);
    }
    
    // Auto-refresh interval dropdown
    document.getElementById('auto-refresh-interval').addEventListener('change', (e) => {
        const interval = parseInt(e.target.value);
        if (interval > 0) {
            CONFIG.autoRefreshInterval = interval;
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
    
    // Time range selectors (delegated event listener for dynamic elements)
    document.addEventListener('change', async (e) => {
        if (e.target.classList.contains('time-range-select')) {
            const deviceId = e.target.dataset.deviceId;
            const timeRangeValue = e.target.value;
            
            // Update stored time range (null for "all time")
            deviceTimeRanges[deviceId] = timeRangeValue === 'null' ? null : parseInt(timeRangeValue);
            
            // Re-render chart with new time range
            // Pass recent readings; the chart function will use hourly samples for longer timeframes
            const deviceReadings = (userData?.readings || []).filter(r => r.device_id === deviceId);
            initializeDeviceChart(deviceId, deviceReadings);
        } else if (e.target.classList.contains('sampling-rate-select')) {
            const deviceId = e.target.dataset.deviceId;
            const newInterval = parseInt(e.target.value);
            
            try {
                // Disable while updating
                e.target.disabled = true;
                const originalText = e.target.options[e.target.selectedIndex].text;
                e.target.options[e.target.selectedIndex].text = 'Saving...';
                
                const headers = await getAuthHeaders();
                const response = await fetch(`${CONFIG.apiBaseUrl}/devices/${deviceId}/config`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ target_interval: newInterval })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to update configuration');
                }
                
                // Show success briefly
                e.target.options[e.target.selectedIndex].text = 'Saved!';
                setTimeout(() => {
                    e.target.options[e.target.selectedIndex].text = originalText;
                    e.target.disabled = false;
                }, 1000);
                
            } catch (error) {
                console.error('Error updating config:', error);
                alert('Failed to update sampling rate. Please try again.');
                e.target.disabled = false;
            }
        }
    });
}

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🌱 GrowSense Dashboard initializing...');
    
    // Set up event listeners
    setupEventListeners();
    
    // Initialize Firebase
    initializeFirebase();
    
    // Check if user is already logged in (handled by onAuthStateChanged)
});

// ========================================
// Export for debugging
// ========================================

window.GrowSense = {
    loadUserData,
    loadUserAdvice,
    signOut,
    config: CONFIG,
    getCurrentUser: () => currentUser,
    getUserDevices: () => userDevices,
    getUserData: () => userData,
    getUserAdvice: () => userAdvice
};

console.log('💡 Tip: Use window.GrowSense to access dashboard functions from console');
