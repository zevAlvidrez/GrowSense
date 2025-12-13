/**
 * Detailed Gap Timeline Analysis
 * Separates hourly samples from actual upload failures
 * Checks 2am-8am window specifically
 */

(function analyzeGapTimeline() {
    console.log('='.repeat(60));
    console.log('Detailed Gap Timeline Analysis');
    console.log('='.repeat(60));

    const userId = 'us2HiruWUkNZ51EaSxHr69Hdps73';
    const cached = JSON.parse(localStorage.getItem(`growsense_cache_${userId}`));
    
    if (!cached) {
        console.error('No cached data');
        return;
    }

    // Separate recent readings from hourly samples
    const recentReadings = cached.readings || [];
    const hourlySamples = cached.hourly_samples || [];
    
    console.log(`\n📊 Data overview:`);
    console.log(`   Recent readings (high-freq): ${recentReadings.length}`);
    console.log(`   Hourly samples (sparse): ${hourlySamples.length}`);
    
    // Focus on recent readings only - these should be every 30-60 seconds
    console.log('\n' + '='.repeat(60));
    console.log('RECENT READINGS ANALYSIS (Expected: every 30-60 seconds)');
    console.log('='.repeat(60));

    // Group by device
    const byDevice = {};
    recentReadings.forEach(r => {
        const deviceId = r.device_id || 'unknown';
        if (!byDevice[deviceId]) byDevice[deviceId] = [];
        byDevice[deviceId].push(r);
    });

    const allGaps = [];
    
    Object.entries(byDevice).forEach(([deviceId, readings]) => {
        readings.sort((a, b) => new Date(a.server_timestamp || a.timestamp) - new Date(b.server_timestamp || b.timestamp));
        
        console.log(`\n📱 ${deviceId} (${readings.length} recent readings):`);
        
        if (readings.length < 2) {
            console.log('   Not enough readings');
            return;
        }
        
        // Find time range
        const firstTime = new Date(readings[0].server_timestamp || readings[0].timestamp);
        const lastTime = new Date(readings[readings.length-1].server_timestamp || readings[readings.length-1].timestamp);
        console.log(`   Time range: ${firstTime.toISOString()} to ${lastTime.toISOString()}`);
        
        // Find gaps > 2 minutes (unexpected for 30-60s uploads)
        const gaps = [];
        for (let i = 1; i < readings.length; i++) {
            const prev = new Date(readings[i-1].server_timestamp || readings[i-1].timestamp);
            const curr = new Date(readings[i].server_timestamp || readings[i].timestamp);
            const gapSeconds = (curr - prev) / 1000;
            
            if (gapSeconds > 120) { // > 2 minutes
                gaps.push({
                    deviceId,
                    start: prev,
                    end: curr,
                    gapMin: gapSeconds / 60,
                    hour: curr.getUTCHours()
                });
            }
        }
        
        console.log(`   Gaps > 2 min: ${gaps.length}`);
        
        // Show gaps in chronological order
        if (gaps.length > 0) {
            console.log('   Timeline of gaps:');
            gaps.forEach(g => {
                const localHour = g.end.getHours(); // Local time
                const utcHour = g.end.getUTCHours();
                console.log(`      ${g.end.toISOString()} (${g.gapMin.toFixed(1)} min) - UTC hour: ${utcHour}, Local hour: ${localHour}`);
            });
        }
        
        allGaps.push(...gaps);
    });

    // ========================================
    // Check 2am-8am specifically (UTC times vary by timezone)
    // Assuming PST: 2am-8am PST = 10:00-16:00 UTC
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('2AM-8AM ANALYSIS (assuming PST timezone)');
    console.log('2am-8am PST = 10:00-16:00 UTC');
    console.log('='.repeat(60));
    
    const nightGaps = allGaps.filter(g => {
        const utcHour = g.end.getUTCHours();
        return utcHour >= 10 && utcHour < 16; // 2am-8am PST
    });
    
    const dayGaps = allGaps.filter(g => {
        const utcHour = g.end.getUTCHours();
        return utcHour < 10 || utcHour >= 16; // Outside 2am-8am PST
    });
    
    console.log(`\n   Gaps during 2am-8am PST (10:00-16:00 UTC): ${nightGaps.length}`);
    console.log(`   Gaps outside that window: ${dayGaps.length}`);
    
    if (nightGaps.length > 0) {
        console.log('\n   Night gaps (2am-8am PST):');
        nightGaps.forEach(g => {
            console.log(`      ${g.deviceId}: ${g.end.toISOString()} (${g.gapMin.toFixed(1)} min)`);
        });
    }

    // ========================================
    // Find when gaps started
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('WHEN DID GAPS START?');
    console.log('='.repeat(60));
    
    if (allGaps.length > 0) {
        allGaps.sort((a, b) => a.end - b.end);
        
        const firstGap = allGaps[0];
        const lastGap = allGaps[allGaps.length - 1];
        
        console.log(`\n   First gap: ${firstGap.end.toISOString()}`);
        console.log(`              Device: ${firstGap.deviceId}, Duration: ${firstGap.gapMin.toFixed(1)} min`);
        console.log(`   Last gap:  ${lastGap.end.toISOString()}`);
        console.log(`              Device: ${lastGap.deviceId}, Duration: ${lastGap.gapMin.toFixed(1)} min`);
        
        // Group gaps by 30-min windows to see pattern
        console.log('\n   Gap frequency by 30-min window:');
        const windows = {};
        allGaps.forEach(g => {
            const windowKey = new Date(Math.floor(g.end.getTime() / (30*60*1000)) * (30*60*1000)).toISOString();
            if (!windows[windowKey]) windows[windowKey] = [];
            windows[windowKey].push(g);
        });
        
        Object.entries(windows).sort((a, b) => a[0].localeCompare(b[0])).forEach(([time, gaps]) => {
            const devices = [...new Set(gaps.map(g => g.deviceId))].join(', ');
            console.log(`      ${time}: ${gaps.length} gaps (${devices})`);
        });
    }

    // ========================================
    // Check hourly samples for overnight patterns
    // ========================================
    console.log('\n' + '='.repeat(60));
    console.log('HOURLY SAMPLES CHECK (overnight stability)');
    console.log('='.repeat(60));
    
    if (hourlySamples.length > 0) {
        // Group by device and check for missing hours
        const hourlyByDevice = {};
        hourlySamples.forEach(r => {
            const deviceId = r.device_id || 'unknown';
            if (!hourlyByDevice[deviceId]) hourlyByDevice[deviceId] = [];
            hourlyByDevice[deviceId].push(r);
        });
        
        Object.entries(hourlyByDevice).forEach(([deviceId, samples]) => {
            samples.sort((a, b) => new Date(a.server_timestamp || a.timestamp) - new Date(b.server_timestamp || b.timestamp));
            
            console.log(`\n   ${deviceId}: ${samples.length} hourly samples`);
            
            // Check for gaps in hourly samples (> 90 minutes = missed hour)
            let missedHours = 0;
            for (let i = 1; i < samples.length; i++) {
                const prev = new Date(samples[i-1].server_timestamp || samples[i-1].timestamp);
                const curr = new Date(samples[i].server_timestamp || samples[i].timestamp);
                const gapMin = (curr - prev) / 60000;
                
                if (gapMin > 90) { // More than 1.5 hours = missed sample
                    const utcHour = curr.getUTCHours();
                    const isNight = utcHour >= 10 && utcHour < 16; // 2am-8am PST
                    console.log(`      Gap: ${gapMin.toFixed(0)} min at ${curr.toISOString()} ${isNight ? '(NIGHT)' : ''}`);
                    missedHours++;
                }
            }
            
            if (missedHours === 0) {
                console.log('      ✅ No missed hourly samples');
            }
        });
    }

    console.log('\n' + '='.repeat(60));
    console.log('SUMMARY');
    console.log('='.repeat(60));
    
    const totalNight = nightGaps.length;
    const totalDay = dayGaps.length;
    
    console.log(`\n   Total gaps in recent readings: ${allGaps.length}`);
    console.log(`   During 2am-8am PST: ${totalNight} (${(totalNight/allGaps.length*100).toFixed(0)}%)`);
    console.log(`   During other hours: ${totalDay} (${(totalDay/allGaps.length*100).toFixed(0)}%)`);
    
    if (totalNight === 0 && totalDay > 0) {
        console.log('\n   ✅ NO gaps during 2am-8am when network was quiet');
        console.log('   → Network congestion during active hours is likely the cause');
    } else if (totalNight > totalDay) {
        console.log('\n   ⚠️ MORE gaps during 2am-8am');
        console.log('   → Might be device sleep/power issues, not network');
    }

    console.log('\n' + '='.repeat(60));
    
    return { allGaps, nightGaps, dayGaps, byDevice };
})();

