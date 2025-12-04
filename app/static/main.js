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
    recentReadingsLimit: 120, // High-res readings to keep
    historicReadingsLimit: 120, // Historic readings to keep
};

// localStorage cache key prefix
const CACHE_KEY_PREFIX = 'growsense_cache_';

// Global state
let firebaseAuth = null;
let currentUser = null;
let idToken = null;
let deviceCharts = {}; // Object to store charts: {deviceId: chart}
let deviceViewModes = {}; // Object to store selected view mode per device: {deviceId: 'recent'|'historic'}
let autoRefreshTimer = null;
let userDevices = [];
let userData = null; // Raw response data
let userAdvice = null;

// Data cache (in-memory)
let dataCache = {
    recent: [],
    historic: [],
    last_fetch_timestamp: null
};

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
                console.log(`Loaded cache for user ${userId}: ${data.recent?.length || 0} recent, ${data.historic?.length || 0} historic`);
                return data;
            }
        }
    } catch (e) {
        console.error('Error loading from localStorage:', e);
    }
    return null;
}

function saveToLocalStorage(userId, cacheData) {
    if (!userId) return;
    try {
        const key = getLocalStorageKey(userId);
        const toSave = {
            user_id: userId,
            cached_at: new Date().toISOString(),
            recent: cacheData.recent || [],
            historic: cacheData.historic || [],
            last_fetch_timestamp: cacheData.last_fetch_timestamp
        };
        localStorage.setItem(key, JSON.stringify(toSave));
        console.log(`Saved cache for user ${userId}: ${toSave.recent.length} recent, ${toSave.historic.length} historic`);
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

// ========================================
// Table display state
// ========================================
let tableDisplayLimit = 20; // How many readings currently shown in table
const TABLE_INCREMENT = 20; // How many more to show when "Load More" clicked

// ========================================
// Firebase Auth Initialization
// ========================================

function initializeFirebase() {
    if (!FIREBASE_CONFIG || !FIREBASE_CONFIG.apiKey) {
        console.error('Firebase config not found. Please set FIREBASE_WEB_CONFIG environment variable.');
        showLoginError('Firebase configuration missing. Please set FIREBASE_WEB_CONFIG environment variable.');
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
    if (!currentUser || currentUser.uid !== user.uid) {
        console.log('[Auth] New user detected, resetting cache');
        dataCache = {
            recent: [],
            historic: [],
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
    if (currentUser?.uid) {
        clearLocalStorageCache(currentUser.uid);
    }
    
    currentUser = null;
    idToken = null;
    userDevices = [];
    userData = null;
    userAdvice = null;
    
    // Clear in-memory cache
    dataCache = {
        recent: [],
        historic: [],
        last_fetch_timestamp: null
    };
    
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
        
        // Fetch recent and historic data in one go
        const url = `${CONFIG.apiBaseUrl}/user_data`;
        
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
        
        // Update cache with response data
        if (data.data) {
            dataCache.recent = data.data.recent || [];
            dataCache.historic = data.data.historic || [];
            dataCache.last_fetch_timestamp = new Date().toISOString();
            
            console.log(`Fetched data: ${dataCache.recent.length} recent, ${dataCache.historic.length} historic`);
        }
        
        return data;
    } catch (error) {
        console.error('Error fetching user data:', error);
        throw error;
    }
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
        
        // Check localStorage for existing cache
        const cachedData = loadFromLocalStorage(userId);
        
        if (cachedData) {
            dataCache.recent = cachedData.recent || [];
            dataCache.historic = cachedData.historic || [];
            dataCache.last_fetch_timestamp = cachedData.last_fetch_timestamp;
            console.log('[Cache] Restored from localStorage');
            
            // Render immediately with cached data
            updateDeviceCards();
            updateUnifiedTable();
        }
        
        // Always fetch fresh data to ensure synchronization
        // The API backend handles minimizing reads via its own strategy
        const [devices, data] = await Promise.all([
            fetchUserDevices(),
            fetchUserData()
        ]);
        
        userDevices = devices.slice(0, CONFIG.maxDevices); // Limit to 4 devices
        userData = data;
        
        // Save updated cache to localStorage
        saveToLocalStorage(userId, dataCache);
        
        // Update displays
        updateDeviceCards();
        updateUnifiedTable();
        
        const totalReadings = (dataCache.recent?.length || 0) + (dataCache.historic?.length || 0);
        updateStatus(`✓ Loaded ${totalReadings} readings`, 'success');
        updateDataCount(totalReadings);
        updateLastUpdated();
        
    } catch (error) {
        console.error('Error loading user data:', error);
        updateStatus(`Error: ${error.message}`, 'error');
        if (error.message.includes('Authentication')) {
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
        
        if (!advice || typeof advice !== 'object') {
            throw new Error('Invalid advice format received');
        }
        
        if (!advice.overall_advice && !advice.device_advice && !advice.insights) {
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
    
    // Preserve open description editor state
    let openEditorState = null;
    const allEditors = grid.querySelectorAll('.description-editor');
    for (const editor of allEditors) {
        const isVisible = editor.style.display === 'block';
        if (isVisible) {
            const section = editor.closest('.device-description-section');
            const textarea = editor.querySelector('.description-textarea');
            if (section && textarea) {
                openEditorState = {
                    deviceId: section.dataset.deviceId,
                    unsavedText: textarea.value
                };
            }
            break; 
        }
    }
    
    grid.innerHTML = '';
    
    if (userDevices.length === 0) {
        grid.innerHTML = '<div class="no-devices-message">No devices registered. Register a device to start monitoring.</div>';
        return;
    }
    
    for (let i = 0; i < Math.min(userDevices.length, CONFIG.maxDevices); i++) {
        const device = userDevices[i];
        const deviceId = device.device_id;
        
        // Get recent readings for this device for the card display
        const deviceReadings = (dataCache.recent || []).filter(r => r.device_id === deviceId);
        const latestReading = deviceReadings[0] || null;
        
        const card = createDeviceCard(device, latestReading, deviceReadings);
        grid.appendChild(card);
        
        // Initialize chart
        if (deviceReadings.length > 0 || (dataCache.historic || []).filter(r => r.device_id === deviceId).length > 0) {
            initializeDeviceChart(deviceId);
        }
    }
    
    // Restore open description editor state
    if (openEditorState) {
        const section = grid.querySelector(
            `.device-description-section[data-device-id="${openEditorState.deviceId}"]`
        );
        if (section) {
            const editor = section.querySelector('.description-editor');
            const toggle = section.querySelector('.description-toggle');
            const textarea = section.querySelector('.description-textarea');
            
            if (editor && toggle && textarea) {
                textarea.value = openEditorState.unsavedText;
                editor.style.display = 'block';
                toggle.style.display = 'none';
                updateCharCount(section);
            }
        }
    }
    
    updateDeviceSpecificAdvice();
}

function createDeviceCard(device, latestReading, readings) {
    const card = document.createElement('div');
    card.className = 'device-card';
    card.id = `device-card-${device.device_id}`;
    
    const lastSeen = device.last_seen ? new Date(device.last_seen) : null;
    const isOnline = lastSeen && (Date.now() - lastSeen.getTime()) < 3600000; // 1 hour
    const statusClass = isOnline ? 'status-online' : 'status-offline';
    const statusText = isOnline ? '● Online' : '○ Offline';
    
    // Default to 'recent' mode if not set
    if (!deviceViewModes[device.device_id]) {
        deviceViewModes[device.device_id] = 'recent';
    }
    const currentMode = deviceViewModes[device.device_id];
    
    const currentInterval = device.target_interval || 30;
    
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
                <label for="view-mode-${device.device_id}">View:</label>
                <select id="view-mode-${device.device_id}" class="view-mode-select" data-device-id="${device.device_id}">
                    <option value="recent" ${currentMode === 'recent' ? 'selected' : ''}>Recent</option>
                    <option value="historic" ${currentMode === 'historic' ? 'selected' : ''}>Historic</option>
                </select>
            </div>
            <div class="control-group">
                <label for="sampling-rate-${device.device_id}">Sampling:</label>
                <select id="sampling-rate-${device.device_id}" class="sampling-rate-select" data-device-id="${device.device_id}">
                    <option value="30" ${currentInterval == 30 ? 'selected' : ''}>30s</option>
                    <option value="60" ${currentInterval == 60 ? 'selected' : ''}>1m</option>
                    <option value="120" ${currentInterval == 120 ? 'selected' : ''}>2m</option>
                    <option value="300" ${currentInterval == 300 ? 'selected' : ''}>5m</option>
                    <option value="600" ${currentInterval == 600 ? 'selected' : ''}>10m</option>
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
        <div class="device-description-section" data-device-id="${device.device_id}">
            <span class="description-toggle">Device description</span>
            <div class="description-editor" style="display: none;">
                <textarea 
                    class="description-textarea" 
                    maxlength="1500" 
                    placeholder="Add a description for this device (max 250 words)..."
                >${device.description || ''}</textarea>
                <div class="description-char-count">
                    <span class="char-count">${(device.description || '').length}</span>/1500
                </div>
                <div class="description-buttons">
                    <button class="description-save-btn">Save</button>
                    <button class="description-cancel-btn">Cancel</button>
                </div>
            </div>
        </div>
    `;
    
    return card;
}

// ========================================
// Chart Functions - Individual Device Charts
// ========================================

function downsampleReadings(readings, maxPoints) {
    if (!readings || readings.length <= maxPoints) {
        return readings;
    }
    
    const stride = Math.ceil(readings.length / maxPoints);
    const sampled = [];
    
    for (let i = 0; i < readings.length; i += stride) {
        sampled.push(readings[i]);
    }
    
    if (sampled[sampled.length - 1] !== readings[readings.length - 1]) {
        sampled.push(readings[readings.length - 1]);
    }
    
    return sampled;
}

function initializeDeviceChart(deviceId) {
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
    
    // Get selected view mode
    const viewMode = deviceViewModes[deviceId] || 'recent';
    let chartReadings = [];
    let viewModeText = viewMode === 'recent' ? 'recent data' : 'historic data';
    
    // Select data source based on mode
    if (viewMode === 'recent') {
        chartReadings = (dataCache.recent || []).filter(r => r.device_id === deviceId);
    } else {
        chartReadings = (dataCache.historic || []).filter(r => r.device_id === deviceId);
    }
    
    // Check if we have any data
    if (chartReadings.length === 0) {
        if (noDataMessageEl) {
            noDataMessageEl.textContent = `No ${viewModeText} available`;
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
    
    // Sort readings by timestamp (oldest first for chart)
    chartReadings.sort((a, b) => {
        const timeA = new Date(a.timestamp || a.server_timestamp).getTime();
        const timeB = new Date(b.timestamp || b.server_timestamp).getTime();
        return timeA - timeB;
    });
    
    // Downsample if needed (though API limits should handle most of this)
    const sortedReadings = downsampleReadings(chartReadings, CONFIG.chartMaxPoints);
    const labels = sortedReadings.map(r => r.timestamp || r.server_timestamp);
    
    // Common chart options
    const commonOptions = {
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
            }
        }
    };

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
                    borderColor: '#4CAF50',
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    yAxisID: 'y',
                    tension: 0.4,
                },
                {
                    label: 'Humidity (%)',
                    data: sortedReadings.map(r => r.humidity),
                    borderColor: '#42A5F5',
                    backgroundColor: 'rgba(66, 165, 245, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                },
                {
                    label: 'Soil Moisture (%)',
                    data: sortedReadings.map(r => r.soil_moisture),
                    borderColor: '#1976D2',
                    backgroundColor: 'rgba(25, 118, 210, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                x: { ...commonOptions.scales.x, display: false }, // Hide X axis labels on top chart
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
                    borderColor: '#FFC107',
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
                    borderColor: '#9C27B0',
                    backgroundColor: 'rgba(156, 39, 176, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.4,
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
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
                    min: 0,
                    suggestedMax: 1.0
                }
            }
        }
    });
}

// ========================================
// Display Updates - Advice
// ========================================

function updateAdviceDisplay() {
    // Always show the advice section
    document.getElementById('advice-section').style.display = 'block';
    
    if (!userAdvice) {
        document.getElementById('general-advice').innerHTML = '<p>Click "Get Advice" to receive plant care recommendations based on your sensor data.</p>';
        document.getElementById('insights-list').innerHTML = '';
        return;
    }
    
    const generalAdviceEl = document.getElementById('general-advice');
    if (userAdvice.overall_advice) {
        let escapedAdvice = userAdvice.overall_advice
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Basic markdown formatting
        escapedAdvice = escapedAdvice.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
        escapedAdvice = escapedAdvice.replace(/\*([^*]+?)\*/g, '<em>$1</em>');
        escapedAdvice = escapedAdvice.replace(/\*\*/g, '');
        
        generalAdviceEl.innerHTML = `<p>${escapedAdvice}</p>`;
    } else {
        generalAdviceEl.innerHTML = '<p>No general advice available.</p>';
    }
    
    const insightsEl = document.getElementById('insights-list');
    if (userAdvice.insights && userAdvice.insights.length > 0) {
        const validInsights = userAdvice.insights.filter(insight => {
            const lower = insight.toLowerCase();
            return !lower.includes('sensor data analyzed successfully') && 
                   !lower.includes('review device-specific recommendations');
        });
        
        if (validInsights.length > 0) {
            insightsEl.innerHTML = '<h3>Insights:</h3><ul>' + 
                validInsights.map(insight => {
                    let escaped = insight
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    
                    escaped = escaped.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
                    escaped = escaped.replace(/\*([^*]+?)\*/g, '<em>$1</em>');
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
    
    // Combine recent data from all devices for the table
    const allReadings = dataCache.recent || [];
    
    if (allReadings.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="no-data">No data available. Click "Refresh Data" to load.</td></tr>';
        updateLoadMoreButton(0, 0);
        return;
    }
    
    const totalReadings = allReadings.length;
    const displayedReadings = allReadings.slice(0, tableDisplayLimit);
    
    displayedReadings.forEach(reading => {
        const row = document.createElement('tr');
        
        const deviceName = reading.device_name || reading.device_id || 'Unknown';
        const timestamp = reading.timestamp || reading.server_timestamp;
        const temp = reading.temperature;
        const humidity = reading.humidity;
        const light = reading.light;
        const soil = reading.soil_moisture;
        
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
    // Just increase the display limit, all data is already in cache (recent)
    // We don't fetch more from server for the "recent" table view
    const allReadings = dataCache.recent || [];
    const totalReadings = allReadings.length;
    
    if (tableDisplayLimit < totalReadings) {
        tableDisplayLimit += TABLE_INCREMENT;
        updateUnifiedTable();
    }
}

async function loadMoreFromFirestore() {
    // Deprecated - we fetch everything upfront now
    // But keeping empty stub or redirecting logic if needed
    console.warn("loadMoreFromFirestore is deprecated in this version");
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
        
        if (diffMs < oneDayMs) {
            return date.toLocaleTimeString('en-US', { 
                hour: 'numeric', 
                minute: '2-digit',
                hour12: true 
            }).toLowerCase();
        }
        
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
    // Optional
}

function clearAllDisplays() {
    document.getElementById('devices-grid').innerHTML = '';
    
    Object.values(deviceCharts).forEach(charts => {
        if (charts.primary) charts.primary.destroy();
        if (charts.secondary) charts.secondary.destroy();
    });
    deviceCharts = {};
    
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '<tr><td colspan="7" class="no-data">No data available</td></tr>';
    
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
    document.getElementById('google-signin-btn').addEventListener('click', signInWithGoogle);
    document.getElementById('logout-btn').addEventListener('click', signOut);
    document.getElementById('get-advice-btn').addEventListener('click', loadUserAdvice);
    document.getElementById('refresh-btn').addEventListener('click', loadUserData);
    
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreReadings);
    }
    
    document.getElementById('auto-refresh-interval').addEventListener('change', (e) => {
        const interval = parseInt(e.target.value);
        if (interval > 0) {
            CONFIG.autoRefreshInterval = interval;
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
    
    // Delegated events for dynamic elements
    document.addEventListener('change', async (e) => {
        if (e.target.classList.contains('view-mode-select')) {
            const deviceId = e.target.dataset.deviceId;
            const mode = e.target.value;
            
            // Update stored mode
            deviceViewModes[deviceId] = mode;
            
            // Re-render chart with new mode
            initializeDeviceChart(deviceId);
        } else if (e.target.classList.contains('sampling-rate-select')) {
            // ... existing sampling rate logic ...
            const deviceId = e.target.dataset.deviceId;
            const newInterval = parseInt(e.target.value);
            
            try {
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
    
    // Device description event handlers
    document.addEventListener('click', async (e) => {
        if (e.target.classList.contains('description-toggle')) {
            const section = e.target.closest('.device-description-section');
            const editor = section.querySelector('.description-editor');
            const textarea = section.querySelector('.description-textarea');
            const deviceId = section.dataset.deviceId;
            
            const device = userDevices.find(d => d.device_id === deviceId);
            textarea.value = device?.description || '';
            updateCharCount(section);
            
            editor.style.display = 'block';
            e.target.style.display = 'none';
            textarea.focus();
        }
        
        if (e.target.classList.contains('description-save-btn')) {
            const section = e.target.closest('.device-description-section');
            const editor = section.querySelector('.description-editor');
            const toggle = section.querySelector('.description-toggle');
            const textarea = section.querySelector('.description-textarea');
            const deviceId = section.dataset.deviceId;
            const newDescription = textarea.value.trim();
            
            const saveBtn = e.target;
            const cancelBtn = section.querySelector('.description-cancel-btn');
            saveBtn.disabled = true;
            cancelBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            try {
                const headers = await getAuthHeaders();
                const response = await fetch(`${CONFIG.apiBaseUrl}/devices/${deviceId}/description`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ description: newDescription })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to save description');
                }
                
                const device = userDevices.find(d => d.device_id === deviceId);
                if (device) {
                    device.description = newDescription;
                }
                
                editor.style.display = 'none';
                toggle.style.display = 'block';
                
            } catch (error) {
                console.error('Error saving description:', error);
                alert('Failed to save description. Please try again.');
            } finally {
                saveBtn.disabled = false;
                cancelBtn.disabled = false;
                saveBtn.textContent = 'Save';
            }
        }
        
        if (e.target.classList.contains('description-cancel-btn')) {
            const section = e.target.closest('.device-description-section');
            const editor = section.querySelector('.description-editor');
            const toggle = section.querySelector('.description-toggle');
            
            editor.style.display = 'none';
            toggle.style.display = 'block';
        }
    });
    
    document.addEventListener('input', (e) => {
        if (e.target.classList.contains('description-textarea')) {
            const section = e.target.closest('.device-description-section');
            updateCharCount(section);
        }
    });
}

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🌱 GrowSense Dashboard initializing...');
    
    setupEventListeners();
    initializeFirebase();
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
    getUserAdvice: () => userAdvice,
    getDataCache: () => dataCache
};

console.log('💡 Tip: Use window.GrowSense to access dashboard functions from console');