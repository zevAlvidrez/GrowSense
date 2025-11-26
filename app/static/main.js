// ========================================
// GrowSense Dashboard JavaScript
// User-centric multi-device dashboard
// ========================================

// Configuration
const CONFIG = {
    apiBaseUrl: window.location.origin,
    autoRefreshInterval: 60000, // 60 seconds
    chartMaxPoints: 50,
    maxDevices: 4, // Maximum devices to display
};

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
    currentUser = null;
    idToken = null;
    userDevices = [];
    userData = null;
    userAdvice = null;
    
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
        const response = await fetch(`${CONFIG.apiBaseUrl}/user_data?limit=200`, {
            headers: headers
        });
        
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
        // Fetch devices and data in parallel
        const [devices, data] = await Promise.all([
            fetchUserDevices(),
            fetchUserData()
        ]);
        
        userDevices = devices.slice(0, CONFIG.maxDevices); // Limit to 4 devices
        userData = data;
        
        // Update displays
        updateDeviceCards();
        updateUnifiedTable();
        updateStatus(`✓ Loaded ${data.total_readings || 0} readings`, 'success');
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
    
    // Initialize time range for this device if not set
    if (!deviceTimeRanges[device.device_id]) {
        deviceTimeRanges[device.device_id] = null; // null = all time
    }
    
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
            <label for="time-range-${device.device_id}">Time Range:</label>
            <select id="time-range-${device.device_id}" class="time-range-select" data-device-id="${device.device_id}">
                <option value="3600000">1 hour</option>
                <option value="86400000">1 day</option>
                <option value="604800000">1 week</option>
                <option value="2592000000">1 month</option>
                <option value="null" selected>All time</option>
            </select>
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
    
    // Filter readings by selected time range
    const timeRange = deviceTimeRanges[deviceId];
    let filteredReadings = [...readings];
    let timeRangeText = 'all time';
    
    if (timeRange) {
        const cutoffTime = Date.now() - timeRange;
        filteredReadings = readings.filter(r => {
            const timestamp = new Date(r.timestamp || r.server_timestamp).getTime();
            return timestamp >= cutoffTime;
        });
        
        // Determine time range text for message
        if (timeRange === 3600000) timeRangeText = 'the past hour';
        else if (timeRange === 86400000) timeRangeText = 'the past day';
        else if (timeRange === 604800000) timeRangeText = 'the past week';
        else if (timeRange === 2592000000) timeRangeText = 'the past month';
    }
    
    // Check if we have any data
    if (filteredReadings.length === 0) {
        if (noDataMessageEl) {
            if (readings.length === 0) {
                noDataMessageEl.textContent = 'No data received';
            } else {
                noDataMessageEl.textContent = `No data received in ${timeRangeText}`;
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
    
    // Sort readings by timestamp (oldest first) and limit to chartMaxPoints
    const sortedReadings = filteredReadings.reverse().slice(-CONFIG.chartMaxPoints);
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
                    ticks: { font: { size: 9 }, min: 0, max: 12 } // Reasonable UV max
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
        return;
    }
    
    // Show up to 50 most recent readings
    const readings = userData.readings.slice(0, 50);
    
    readings.forEach(reading => {
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
    document.addEventListener('change', (e) => {
        if (e.target.classList.contains('time-range-select')) {
            const deviceId = e.target.dataset.deviceId;
            const timeRangeValue = e.target.value;
            
            // Update stored time range (null for "all time")
            deviceTimeRanges[deviceId] = timeRangeValue === 'null' ? null : parseInt(timeRangeValue);
            
            // Re-render chart with new time range
            const deviceReadings = (userData.readings || []).filter(r => r.device_id === deviceId);
            if (deviceReadings.length > 0) {
                initializeDeviceChart(deviceId, deviceReadings);
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
