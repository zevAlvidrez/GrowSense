/**
 * GrowSense Cached Data Analysis Script
 * 
 * Run this in the browser console while logged into growsenseuser@gmail.com
 * This reads ONLY from localStorage - NO database operations.
 * 
 * Usage: 
 * 1. Open the GrowSense dashboard in your browser
 * 2. Login as growsenseuser@gmail.com
 * 3. Open Developer Console (Cmd+Option+J on Mac, F12 on Windows)
 * 4. Copy and paste this entire script
 * 5. Press Enter to run
 */

(function analyzeCachedData() {
    console.log('='.repeat(60));
    console.log('GrowSense Cached Data Analysis');
    console.log('Analyzing data from 11pm December 1st, 2025 onwards');
    console.log('Reading from localStorage ONLY - no database operations');
    console.log('='.repeat(60));
    console.log('');

    // Find the cache for growsenseuser
    const userId = 'us2HiruWUkNZ51EaSxHr69Hdps73'; // growsenseuser@gmail.com
    const cacheKey = `growsense_cache_${userId}`;
    const cached = localStorage.getItem(cacheKey);
    
    if (!cached) {
        console.error('❌ No cached data found for growsenseuser@gmail.com');
        console.log('Make sure you are logged in and have loaded the dashboard at least once.');
        return;
    }
    
    const cacheData = JSON.parse(cached);
    console.log(`✅ Found cached data:`);
    console.log(`   - Cached at: ${cacheData.cached_at}`);
    console.log(`   - Recent readings: ${cacheData.readings?.length || 0}`);
    console.log(`   - Hourly samples: ${cacheData.hourly_samples?.length || 0}`);
    console.log('');

    // Combine all readings
    const allReadings = [
        ...(cacheData.readings || []),
        ...(cacheData.hourly_samples || [])
    ];
    
    // Filter to only data from 11pm Dec 1st onwards
    const cutoffDate = new Date('2025-12-01T23:00:00Z');
    const filteredReadings = allReadings.filter(r => {
        const timestamp = new Date(r.server_timestamp || r.timestamp);
        return timestamp >= cutoffDate;
    });
    
    console.log(`📊 Filtered to ${filteredReadings.length} readings from 11pm Dec 1st onwards`);
    console.log('');

    // Group by device
    const byDevice = {};
    filteredReadings.forEach(r => {
        const deviceId = r.device_id || 'unknown';
        if (!byDevice[deviceId]) {
            byDevice[deviceId] = [];
        }
        byDevice[deviceId].push(r);
    });
    
    const deviceIds = Object.keys(byDevice);
    console.log(`📱 Found ${deviceIds.length} devices: ${deviceIds.join(', ')}`);
    console.log('');

    // ========================================
    // ANALYSIS 1: Missing Fields
    // ========================================
    console.log('='.repeat(60));
    console.log('ANALYSIS 1: Missing Fields by Device');
    console.log('='.repeat(60));
    
    const fields = ['temperature', 'humidity', 'light', 'soil_moisture', 'uv_light'];
    const missingByDevice = {};
    const missingByField = {};
    const missingByHour = {};
    
    fields.forEach(f => missingByField[f] = { total: 0, devices: {} });
    
    deviceIds.forEach(deviceId => {
        const readings = byDevice[deviceId];
        missingByDevice[deviceId] = { total: readings.length, missing: {} };
        
        fields.forEach(field => {
            missingByDevice[deviceId].missing[field] = 0;
            missingByField[field].devices[deviceId] = 0;
        });
        
        readings.forEach(r => {
            const hour = new Date(r.server_timestamp || r.timestamp).getHours();
            if (!missingByHour[hour]) {
                missingByHour[hour] = { total: 0, missing: {} };
                fields.forEach(f => missingByHour[hour].missing[f] = 0);
            }
            missingByHour[hour].total++;
            
            fields.forEach(field => {
                // Check both top-level and raw_json
                let value = r[field];
                if (value === undefined || value === null) {
                    if (r.raw_json && r.raw_json[field] !== undefined) {
                        value = r.raw_json[field];
                    }
                }
                
                if (value === undefined || value === null) {
                    missingByDevice[deviceId].missing[field]++;
                    missingByField[field].total++;
                    missingByField[field].devices[deviceId]++;
                    missingByHour[hour].missing[field]++;
                }
            });
        });
    });
    
    // Print missing by device
    deviceIds.forEach(deviceId => {
        const data = missingByDevice[deviceId];
        console.log(`\n📱 ${deviceId} (${data.total} readings):`);
        fields.forEach(field => {
            const missing = data.missing[field];
            const pct = ((missing / data.total) * 100).toFixed(1);
            if (missing > 0) {
                console.log(`   ❌ ${field}: ${missing} missing (${pct}%)`);
            } else {
                console.log(`   ✅ ${field}: all present`);
            }
        });
    });
    
    // Print missing by field (cross-device)
    console.log('\n' + '-'.repeat(40));
    console.log('Missing by Field (across all devices):');
    fields.forEach(field => {
        const data = missingByField[field];
        if (data.total > 0) {
            console.log(`\n❌ ${field}: ${data.total} total missing`);
            Object.entries(data.devices).forEach(([dev, count]) => {
                if (count > 0) console.log(`      - ${dev}: ${count}`);
            });
        }
    });

    // ========================================
    // ANALYSIS 2: Upload Frequency
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('ANALYSIS 2: Upload Frequency Analysis');
    console.log('='.repeat(60));
    
    deviceIds.forEach(deviceId => {
        const readings = byDevice[deviceId];
        
        // Sort by timestamp
        readings.sort((a, b) => {
            const ta = new Date(a.server_timestamp || a.timestamp).getTime();
            const tb = new Date(b.server_timestamp || b.timestamp).getTime();
            return ta - tb;
        });
        
        console.log(`\n📱 ${deviceId} (${readings.length} readings):`);
        
        if (readings.length < 2) {
            console.log('   Not enough data for frequency analysis');
            return;
        }
        
        // Calculate gaps between consecutive readings
        const gaps = [];
        for (let i = 1; i < readings.length; i++) {
            const prev = new Date(readings[i-1].server_timestamp || readings[i-1].timestamp).getTime();
            const curr = new Date(readings[i].server_timestamp || readings[i].timestamp).getTime();
            const gapSeconds = (curr - prev) / 1000;
            gaps.push({
                gapSeconds,
                timestamp: readings[i].server_timestamp || readings[i].timestamp,
                hour: new Date(curr).getHours()
            });
        }
        
        // Statistics
        const avgGap = gaps.reduce((sum, g) => sum + g.gapSeconds, 0) / gaps.length;
        const minGap = Math.min(...gaps.map(g => g.gapSeconds));
        const maxGap = Math.max(...gaps.map(g => g.gapSeconds));
        
        console.log(`   Average interval: ${avgGap.toFixed(1)}s`);
        console.log(`   Min interval: ${minGap.toFixed(1)}s`);
        console.log(`   Max interval: ${maxGap.toFixed(1)}s`);
        
        // Find large gaps (> 2 minutes)
        const largeGaps = gaps.filter(g => g.gapSeconds > 120);
        if (largeGaps.length > 0) {
            console.log(`   ⚠️ ${largeGaps.length} gaps > 2 minutes:`);
            largeGaps.slice(0, 10).forEach(g => {
                const mins = (g.gapSeconds / 60).toFixed(1);
                console.log(`      - ${mins} min gap at ${g.timestamp}`);
            });
            if (largeGaps.length > 10) {
                console.log(`      ... and ${largeGaps.length - 10} more`);
            }
        } else {
            console.log(`   ✅ No gaps > 2 minutes`);
        }
        
        // Gaps by hour of day
        const gapsByHour = {};
        gaps.forEach(g => {
            if (!gapsByHour[g.hour]) {
                gapsByHour[g.hour] = [];
            }
            gapsByHour[g.hour].push(g.gapSeconds);
        });
        
        // Find hours with unusual gaps
        const hourlyAvgs = Object.entries(gapsByHour).map(([hour, gapList]) => ({
            hour: parseInt(hour),
            avgGap: gapList.reduce((s, g) => s + g, 0) / gapList.length,
            count: gapList.length,
            maxGap: Math.max(...gapList)
        }));
        
        const problematicHours = hourlyAvgs.filter(h => h.avgGap > avgGap * 1.5 || h.maxGap > 300);
        if (problematicHours.length > 0) {
            console.log(`   ⏰ Hours with irregular timing:`);
            problematicHours.forEach(h => {
                console.log(`      - ${h.hour}:00: avg ${h.avgGap.toFixed(1)}s, max ${h.maxGap.toFixed(1)}s (${h.count} readings)`);
            });
        }
    });

    // ========================================
    // ANALYSIS 3: Cross-Device Time Patterns
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('ANALYSIS 3: Time-of-Day Patterns (Cross-Device)');
    console.log('='.repeat(60));
    
    // Aggregate missing data by hour across all devices
    console.log('\nMissing readings by hour of day (all devices combined):');
    const sortedHours = Object.entries(missingByHour)
        .sort((a, b) => parseInt(a[0]) - parseInt(b[0]));
    
    sortedHours.forEach(([hour, data]) => {
        const totalMissing = Object.values(data.missing).reduce((s, v) => s + v, 0);
        if (totalMissing > 0 || data.total > 5) {
            const pct = ((totalMissing / (data.total * fields.length)) * 100).toFixed(1);
            console.log(`   ${hour.padStart(2, '0')}:00 - ${data.total} readings, ${totalMissing} missing fields (${pct}%)`);
        }
    });

    // ========================================
    // SUMMARY
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('SUMMARY');
    console.log('='.repeat(60));
    
    // Identify patterns
    const deviceMissingTotals = Object.entries(missingByDevice).map(([id, data]) => ({
        id,
        totalMissing: Object.values(data.missing).reduce((s, v) => s + v, 0),
        total: data.total
    }));
    
    const worstDevice = deviceMissingTotals.reduce((worst, d) => 
        d.totalMissing > (worst?.totalMissing || 0) ? d : worst, null);
    
    const fieldMissingTotals = Object.entries(missingByField).map(([field, data]) => ({
        field,
        totalMissing: data.total
    }));
    
    const worstField = fieldMissingTotals.reduce((worst, f) => 
        f.totalMissing > (worst?.totalMissing || 0) ? f : worst, null);
    
    console.log('\n📋 Key Findings:');
    
    if (worstDevice && worstDevice.totalMissing > 0) {
        console.log(`   • Device with most missing: ${worstDevice.id} (${worstDevice.totalMissing} missing fields)`);
    } else {
        console.log(`   • ✅ No devices have missing fields`);
    }
    
    if (worstField && worstField.totalMissing > 0) {
        console.log(`   • Sensor with most missing: ${worstField.field} (${worstField.totalMissing} missing)`);
    } else {
        console.log(`   • ✅ No sensors have missing readings`);
    }
    
    // Check if issues are correlated
    const totalReadings = filteredReadings.length;
    const totalMissingAll = Object.values(missingByField).reduce((s, f) => s + f.total, 0);
    
    console.log(`\n📊 Overall Stats:`);
    console.log(`   • Total readings analyzed: ${totalReadings}`);
    console.log(`   • Total missing fields: ${totalMissingAll}`);
    console.log(`   • Missing rate: ${((totalMissingAll / (totalReadings * fields.length)) * 100).toFixed(2)}%`);
    
    console.log('\n' + '='.repeat(60));
    console.log('Analysis complete. No database operations were performed.');
    console.log('='.repeat(60));
    
    // Return data for further analysis if needed
    return {
        cacheData,
        filteredReadings,
        byDevice,
        missingByDevice,
        missingByField,
        missingByHour
    };
})();

