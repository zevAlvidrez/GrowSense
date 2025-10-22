// ========================================
// GrowSense Dashboard JavaScript
// Easy to customize and extend
// ========================================

// Configuration
const CONFIG = {
    apiBaseUrl: window.location.origin, // Use current host (works locally and on Render)
    autoRefreshInterval: 60000, // 60 seconds (change this to adjust refresh rate)
    chartMaxPoints: 50, // Maximum points to show on chart (change for more/less detail)
};

// Global state
let chart = null;
let autoRefreshTimer = null;
let currentDeviceId = 'test_device';
let currentLimit = 50;

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🌱 GrowSense Dashboard initialized');
    
    // Set up event listeners
    setupEventListeners();
    
    // Initialize chart
    initializeChart();
    
    // Load initial data
    fetchAndDisplayData();
    
    // Start auto-refresh if enabled
    if (document.getElementById('auto-refresh-toggle').checked) {
        startAutoRefresh();
    }
});

// ========================================
// Event Listeners
// ========================================

function setupEventListeners() {
    // Device selection
    document.getElementById('device-select').addEventListener('change', (e) => {
        currentDeviceId = e.target.value;
        fetchAndDisplayData();
    });
    
    // Limit selection
    document.getElementById('limit-select').addEventListener('change', (e) => {
        currentLimit = parseInt(e.target.value);
        fetchAndDisplayData();
    });
    
    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        fetchAndDisplayData();
    });
    
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
// Data Fetching
// ========================================

async function fetchAndDisplayData() {
    updateStatus('Loading data...', 'loading');
    
    try {
        const url = `${CONFIG.apiBaseUrl}/get_data?device_id=${currentDeviceId}&limit=${currentLimit}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.readings.length > 0) {
            // Update all display sections
            updateCurrentReadings(data.readings[0]); // Most recent reading
            updateChart(data.readings);
            updateTable(data.readings);
            updateStatus(`✓ Loaded ${data.count} readings`, 'success');
            updateDataCount(data.count);
            updateLastUpdated();
        } else {
            updateStatus('No data available for this device', 'warning');
            clearDisplays();
        }
    } catch (error) {
        console.error('Error fetching data:', error);
        updateStatus(`Error: ${error.message}`, 'error');
        clearDisplays();
    }
}

// ========================================
// Display Updates - Current Readings
// ========================================

function updateCurrentReadings(reading) {
    // Update temperature
    const temp = reading.temperature;
    document.getElementById('current-temp').textContent = 
        temp !== null && temp !== undefined ? temp.toFixed(1) : '--';
    
    // Update humidity
    const humidity = reading.humidity;
    document.getElementById('current-humidity').textContent = 
        humidity !== null && humidity !== undefined ? humidity.toFixed(1) : '--';
    
    // Update light
    const light = reading.light;
    document.getElementById('current-light').textContent = 
        light !== null && light !== undefined ? Math.round(light) : '--';
    
    // Update soil moisture
    const soil = reading.soil_moisture;
    document.getElementById('current-soil').textContent = 
        soil !== null && soil !== undefined ? soil.toFixed(1) : '--';
}

// ========================================
// Display Updates - Chart
// ========================================

function initializeChart() {
    const ctx = document.getElementById('sensor-chart').getContext('2d');
    
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#FF6384',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    yAxisID: 'y',
                },
                {
                    label: 'Humidity (%)',
                    data: [],
                    borderColor: '#36A2EB',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    yAxisID: 'y',
                },
                {
                    label: 'Soil Moisture (%)',
                    data: [],
                    borderColor: '#4BC0C0',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    yAxisID: 'y',
                },
                {
                    label: 'Light (lux)',
                    data: [],
                    borderColor: '#FFCE56',
                    backgroundColor: 'rgba(255, 206, 86, 0.1)',
                    yAxisID: 'y1',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        title: (context) => {
                            return formatTimestamp(context[0].label);
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        callback: function(value, index, values) {
                            // Show abbreviated timestamps
                            const label = this.getLabelForValue(value);
                            return formatTimestampShort(label);
                        }
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Temperature / Humidity / Soil (%)'
                    },
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Light (lux)'
                    },
                    grid: {
                        drawOnChartArea: false,
                    },
                }
            }
        }
    });
}

function updateChart(readings) {
    // Sort readings by timestamp (oldest first for chart)
    const sortedReadings = [...readings].reverse();
    
    // Limit to max points for performance
    const limitedReadings = sortedReadings.slice(-CONFIG.chartMaxPoints);
    
    // Extract data
    const labels = limitedReadings.map(r => r.timestamp || r.server_timestamp);
    const temperatures = limitedReadings.map(r => r.temperature);
    const humidities = limitedReadings.map(r => r.humidity);
    const soilMoistures = limitedReadings.map(r => r.soil_moisture);
    const lights = limitedReadings.map(r => r.light);
    
    // Update chart
    chart.data.labels = labels;
    chart.data.datasets[0].data = temperatures;
    chart.data.datasets[1].data = humidities;
    chart.data.datasets[2].data = soilMoistures;
    chart.data.datasets[3].data = lights;
    chart.update();
}

// ========================================
// Display Updates - Table
// ========================================

function updateTable(readings) {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    
    readings.forEach(reading => {
        const row = document.createElement('tr');
        
        const timestamp = reading.timestamp || reading.server_timestamp;
        const temp = reading.temperature;
        const humidity = reading.humidity;
        const light = reading.light;
        const soil = reading.soil_moisture;
        
        row.innerHTML = `
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

function formatTimestampShort(timestamp) {
    if (!timestamp) return '--';
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    } catch (e) {
        return timestamp;
    }
}

function updateStatus(message, type = 'info') {
    const statusEl = document.getElementById('status-message');
    statusEl.textContent = message;
    
    // Remove previous type classes
    statusEl.classList.remove('loading', 'success', 'error', 'warning');
    
    // Add new type class
    if (type) {
        statusEl.classList.add(type);
    }
}

function updateDataCount(count) {
    document.getElementById('data-count').textContent = `${count} readings`;
}

function updateLastUpdated() {
    const now = new Date().toLocaleTimeString();
    document.getElementById('last-updated').textContent = `Last updated: ${now}`;
}

function clearDisplays() {
    // Clear current readings
    document.getElementById('current-temp').textContent = '--';
    document.getElementById('current-humidity').textContent = '--';
    document.getElementById('current-light').textContent = '--';
    document.getElementById('current-soil').textContent = '--';
    
    // Clear chart
    if (chart) {
        chart.data.labels = [];
        chart.data.datasets.forEach(dataset => {
            dataset.data = [];
        });
        chart.update();
    }
    
    // Clear table
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '<tr><td colspan="5" class="no-data">No data available</td></tr>';
}

// ========================================
// Auto-Refresh Functions
// ========================================

function startAutoRefresh() {
    stopAutoRefresh(); // Clear any existing timer
    autoRefreshTimer = setInterval(() => {
        console.log('Auto-refreshing data...');
        fetchAndDisplayData();
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
// Export functions for easy extension
// (You can call these from browser console)
// ========================================

window.GrowSense = {
    fetchData: fetchAndDisplayData,
    updateChart: updateChart,
    config: CONFIG,
    getCurrentDeviceId: () => currentDeviceId,
    setDeviceId: (id) => {
        currentDeviceId = id;
        document.getElementById('device-select').value = id;
        fetchAndDisplayData();
    }
};

console.log('💡 Tip: Use window.GrowSense to access dashboard functions from console');

