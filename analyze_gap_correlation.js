/**
 * GrowSense Gap Correlation Analysis
 * 
 * Analyzes whether upload gaps are correlated across devices
 * (suggesting network/server issues) or device-specific (suggesting hardware issues)
 * 
 * Run in browser console while logged into growsenseuser@gmail.com
 */

(function analyzeGapCorrelation() {
    console.log('='.repeat(60));
    console.log('Gap Correlation Analysis');
    console.log('='.repeat(60));
    console.log('');

    const userId = 'us2HiruWUkNZ51EaSxHr69Hdps73';
    const cacheKey = `growsense_cache_${userId}`;
    const cached = localStorage.getItem(cacheKey);
    
    if (!cached) {
        console.error('No cached data found');
        return;
    }
    
    const cacheData = JSON.parse(cached);
    const cutoffDate = new Date('2025-12-01T23:00:00Z');
    
    // Get only RECENT readings (not hourly samples) for accurate frequency analysis
    const recentReadings = (cacheData.readings || []).filter(r => {
        const timestamp = new Date(r.server_timestamp || r.timestamp);
        return timestamp >= cutoffDate;
    });
    
    console.log(`Analyzing ${recentReadings.length} recent readings (excluding hourly samples)`);
    console.log('');

    // Group by device
    const byDevice = {};
    recentReadings.forEach(r => {
        const deviceId = r.device_id || 'unknown';
        if (!byDevice[deviceId]) byDevice[deviceId] = [];
        byDevice[deviceId].push(r);
    });

    // ========================================
    // ANALYSIS 1: Device Configuration Check
    // ========================================
    console.log('='.repeat(60));
    console.log('ANALYSIS 1: Device Upload Patterns');
    console.log('='.repeat(60));
    
    Object.entries(byDevice).forEach(([deviceId, readings]) => {
        readings.sort((a, b) => new Date(a.server_timestamp || a.timestamp) - new Date(b.server_timestamp || b.timestamp));
        
        const gaps = [];
        for (let i = 1; i < readings.length; i++) {
            const prev = new Date(readings[i-1].server_timestamp || readings[i-1].timestamp);
            const curr = new Date(readings[i].server_timestamp || readings[i].timestamp);
            gaps.push((curr - prev) / 1000);
        }
        
        if (gaps.length === 0) return;
        
        // Find the mode (most common interval) - likely the configured interval
        const roundedGaps = gaps.map(g => Math.round(g / 10) * 10); // Round to nearest 10s
        const gapCounts = {};
        roundedGaps.forEach(g => gapCounts[g] = (gapCounts[g] || 0) + 1);
        const modeGap = Object.entries(gapCounts).sort((a, b) => b[1] - a[1])[0];
        
        console.log(`\n📱 ${deviceId}:`);
        console.log(`   Readings in cache: ${readings.length}`);
        console.log(`   Most common interval: ${modeGap[0]}s (${modeGap[1]} occurrences)`);
        console.log(`   Likely configured for: ${modeGap[0]}s uploads`);
        
        // Check for duplicate timestamps
        const duplicates = gaps.filter(g => g === 0).length;
        if (duplicates > 0) {
            console.log(`   ⚠️ ${duplicates} duplicate timestamps detected!`);
        }
    });

    // ========================================
    // ANALYSIS 2: Find Correlated Gaps
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('ANALYSIS 2: Correlated Gaps Across Devices');
    console.log('='.repeat(60));
    console.log('\nLooking for times when multiple devices had gaps simultaneously...\n');
    
    // Create timeline of all readings
    const timeline = [];
    Object.entries(byDevice).forEach(([deviceId, readings]) => {
        readings.forEach(r => {
            timeline.push({
                deviceId,
                timestamp: new Date(r.server_timestamp || r.timestamp)
            });
        });
    });
    timeline.sort((a, b) => a.timestamp - b.timestamp);
    
    // Find 5-minute windows where devices went silent
    const windowSize = 5 * 60 * 1000; // 5 minutes
    const silentWindows = [];
    
    // For each device, find gaps > 2 minutes
    const deviceGaps = {};
    Object.entries(byDevice).forEach(([deviceId, readings]) => {
        readings.sort((a, b) => new Date(a.server_timestamp || a.timestamp) - new Date(b.server_timestamp || b.timestamp));
        deviceGaps[deviceId] = [];
        
        for (let i = 1; i < readings.length; i++) {
            const prev = new Date(readings[i-1].server_timestamp || readings[i-1].timestamp);
            const curr = new Date(readings[i].server_timestamp || readings[i].timestamp);
            const gapMs = curr - prev;
            
            if (gapMs > 2 * 60 * 1000) { // Gap > 2 minutes
                deviceGaps[deviceId].push({
                    start: prev,
                    end: curr,
                    durationMin: gapMs / 60000
                });
            }
        }
    });
    
    // Find overlapping gaps between devices
    const deviceIds = Object.keys(deviceGaps);
    const correlatedGaps = [];
    
    for (let i = 0; i < deviceIds.length; i++) {
        for (let j = i + 1; j < deviceIds.length; j++) {
            const device1 = deviceIds[i];
            const device2 = deviceIds[j];
            
            deviceGaps[device1].forEach(gap1 => {
                deviceGaps[device2].forEach(gap2 => {
                    // Check if gaps overlap
                    const overlapStart = Math.max(gap1.start.getTime(), gap2.start.getTime());
                    const overlapEnd = Math.min(gap1.end.getTime(), gap2.end.getTime());
                    
                    if (overlapStart < overlapEnd) {
                        correlatedGaps.push({
                            devices: [device1, device2],
                            overlapStart: new Date(overlapStart),
                            overlapEnd: new Date(overlapEnd),
                            overlapMinutes: (overlapEnd - overlapStart) / 60000,
                            gap1Duration: gap1.durationMin,
                            gap2Duration: gap2.durationMin
                        });
                    }
                });
            });
        }
    }
    
    if (correlatedGaps.length > 0) {
        console.log(`⚠️ Found ${correlatedGaps.length} correlated gaps (devices went silent together):\n`);
        
        // Deduplicate by time window
        const uniqueWindows = [];
        correlatedGaps.forEach(gap => {
            const existing = uniqueWindows.find(w => 
                Math.abs(w.overlapStart.getTime() - gap.overlapStart.getTime()) < 60000
            );
            if (existing) {
                if (!existing.devices.includes(gap.devices[0])) existing.devices.push(gap.devices[0]);
                if (!existing.devices.includes(gap.devices[1])) existing.devices.push(gap.devices[1]);
            } else {
                uniqueWindows.push({...gap, devices: [...gap.devices]});
            }
        });
        
        uniqueWindows.slice(0, 15).forEach(gap => {
            const time = gap.overlapStart.toISOString();
            console.log(`   ${time}`);
            console.log(`      Devices affected: ${gap.devices.join(', ')}`);
            console.log(`      Overlap duration: ${gap.overlapMinutes.toFixed(1)} min`);
            console.log('');
        });
        
        console.log('\n🔍 INTERPRETATION:');
        console.log('   Correlated gaps suggest a SHARED issue:');
        console.log('   • WiFi/Router problems');
        console.log('   • Server unavailable');
        console.log('   • Power issues affecting multiple devices');
    } else {
        console.log('✅ No correlated gaps found - gaps are device-specific');
    }

    // ========================================
    // ANALYSIS 3: Gap Pattern by Time of Day
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('ANALYSIS 3: Gap Heatmap by Hour');
    console.log('='.repeat(60));
    
    const gapsByHour = {};
    for (let h = 0; h < 24; h++) gapsByHour[h] = { count: 0, devices: new Set() };
    
    Object.entries(deviceGaps).forEach(([deviceId, gaps]) => {
        gaps.forEach(gap => {
            const hour = gap.start.getHours();
            gapsByHour[hour].count++;
            gapsByHour[hour].devices.add(deviceId);
        });
    });
    
    console.log('\nGaps by hour (local time):');
    for (let h = 0; h < 24; h++) {
        const data = gapsByHour[h];
        if (data.count > 0) {
            const bar = '█'.repeat(Math.min(data.count, 20));
            const devices = Array.from(data.devices).join(', ');
            console.log(`   ${String(h).padStart(2, '0')}:00 ${bar} (${data.count} gaps) - ${devices}`);
        }
    }

    // ========================================
    // SUMMARY
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('SUMMARY: Root Cause Analysis');
    console.log('='.repeat(60));
    
    const totalGaps = Object.values(deviceGaps).reduce((sum, gaps) => sum + gaps.length, 0);
    const correlatedCount = correlatedGaps.length;
    const correlationRate = totalGaps > 0 ? (correlatedCount / totalGaps * 100).toFixed(1) : 0;
    
    console.log(`\n📊 Statistics:`);
    console.log(`   Total gaps > 2min: ${totalGaps}`);
    console.log(`   Correlated gaps: ${correlatedCount} (${correlationRate}%)`);
    
    console.log(`\n🔍 Likely Causes:`);
    
    if (correlationRate > 50) {
        console.log('   ⚠️ HIGH correlation - likely NETWORK/SERVER issue');
        console.log('   → Check WiFi stability, router logs, server uptime');
    } else if (correlationRate > 20) {
        console.log('   ⚠️ MODERATE correlation - mix of network and device issues');
        console.log('   → Check both network stability and individual device health');
    } else {
        console.log('   ✅ LOW correlation - likely DEVICE-SPECIFIC issues');
        console.log('   → Check individual device power, sensor connections');
    }
    
    // Check device 3 specifically
    const device3Gaps = deviceGaps['garden_device_3'] || [];
    if (device3Gaps.length > 10) {
        console.log(`\n   ⚠️ garden_device_3 has ${device3Gaps.length} gaps`);
        console.log('   → This device may be configured for longer intervals');
        console.log('   → Or experiencing frequent disconnections');
    }
    
    console.log('\n' + '='.repeat(60));
    
    return { deviceGaps, correlatedGaps, gapsByHour };
})();

