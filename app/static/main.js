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
    Object.values(deviceCharts).forEach(chart => chart.destroy());
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
        userAdvice = advice;
        updateAdviceDisplay();
    } catch (error) {
        console.error('Error loading advice:', error);
        updateStatus(`Error loading advice: ${error.message}`, 'error');
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
            <div class="device-reading">
                <span class="reading-icon">☀️</span>
                <span class="reading-value">${latestReading?.light ? Math.round(latestReading.light) : '--'}</span>
                <span class="reading-unit">lux</span>
            </div>
            <div class="device-reading">
                <span class="reading-icon">🌿</span>
                <span class="reading-value">${latestReading?.soil_moisture?.toFixed(1) || '--'}</span>
                <span class="reading-unit">%</span>
            </div>
        </div>
        <div class="device-chart-container">
            <canvas id="chart-${device.device_id}"></canvas>
        </div>
        <div id="device-advice-${device.device_id}" class="device-advice" style="display: none;"></div>
    `;
    
    return card;
}

// ========================================
// Chart Functions - Individual Device Charts
// ========================================

function initializeDeviceChart(deviceId, readings) {
    const canvasId = `chart-${deviceId}`;
    const canvas = document.getElementById(canvasId);
    
    if (!canvas) {
        console.warn(`Canvas not found for device ${deviceId}`);
        return;
    }
    
    // Destroy existing chart if any
    if (deviceCharts[deviceId]) {
        deviceCharts[deviceId].destroy();
    }
    
    // Sort readings by timestamp (oldest first)
    const sortedReadings = [...readings].reverse().slice(-CONFIG.chartMaxPoints);
    
    const labels = sortedReadings.map(r => r.timestamp || r.server_timestamp);
    
    const ctx = canvas.getContext('2d');
    deviceCharts[deviceId] = new Chart(ctx, {
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
                    borderColor: '#42A5F5', // Blue
                    backgroundColor: 'rgba(66, 165, 245, 0.1)',
                    yAxisID: 'y',
                    tension: 0.4,
                },
                {
                    label: 'Soil Moisture (%)',
                    data: sortedReadings.map(r => r.soil_moisture),
                    borderColor: '#66BB6A', // Light green
                    backgroundColor: 'rgba(102, 187, 106, 0.1)',
                    yAxisID: 'y',
                    tension: 0.4,
                },
                {
                    label: 'Light (lux)',
                    data: sortedReadings.map(r => r.light),
                    borderColor: '#FFC107', // Yellow
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
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
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        maxTicksLimit: 6,
                        font: {
                            size: 10
                        }
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    ticks: {
                        font: {
                            size: 10
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        font: {
                            size: 10
                        }
                    }
                }
            }
        }
    });
}

// ========================================
// Display Updates - Advice
// ========================================

function updateAdviceDisplay() {
    if (!userAdvice) {
        document.getElementById('advice-section').style.display = 'none';
        return;
    }
    
    document.getElementById('advice-section').style.display = 'block';
    
    // Update general advice
    const generalAdviceEl = document.getElementById('general-advice');
    if (userAdvice.overall_advice) {
        generalAdviceEl.innerHTML = `<p>${userAdvice.overall_advice}</p>`;
    } else {
        generalAdviceEl.innerHTML = '<p>No general advice available.</p>';
    }
    
    // Update insights
    const insightsEl = document.getElementById('insights-list');
    if (userAdvice.insights && userAdvice.insights.length > 0) {
        insightsEl.innerHTML = '<h3>Insights:</h3><ul>' + 
            userAdvice.insights.map(insight => `<li>${insight}</li>`).join('') + 
            '</ul>';
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
        tbody.innerHTML = '<tr><td colspan="6" class="no-data">No data available. Click "Refresh Data" to load.</td></tr>';
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
        
        row.innerHTML = `
            <td>${deviceName}</td>
            <td>${formatTimestamp(timestamp)}</td>
            <td>${temp !== null && temp !== undefined ? temp.toFixed(1) : '--'}</td>
            <td>${humidity !== null && humidity !== undefined ? humidity.toFixed(1) : '--'}</td>
            <td>${light !== null && light !== undefined ? Math.round(light) : '--'}</td>
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
    Object.values(deviceCharts).forEach(chart => chart.destroy());
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
    
    // Auto-refresh toggle
    document.getElementById('auto-refresh-toggle').addEventListener('change', (e) => {
        if (e.target.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
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
