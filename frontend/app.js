// Configuration
const BASE_URL = "https://farmer-alert-api.onrender.com/api";
let moistureChart = null;

// Security Check
const token = localStorage.getItem('farm_token');
if (!token) window.location.href = 'login.html';

function logout() {
    localStorage.removeItem('farm_token');
    window.location.href = 'login.html';
}

async function fetchAllData() {
    try {
        // 1. Ask the Bouncer for the Dashboard Summary (All Sensors)
        const dashResponse = await fetch(`${BASE_URL}/dashboard`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (dashResponse.status === 401) logout();
        if (!dashResponse.ok) throw new Error("Failed to fetch dashboard");

        const sensorsData = await dashResponse.json();

        // 2. Clear the "Loading" text and render the individual widgets
        const container = document.getElementById('sensor-widgets-container');
        container.innerHTML = "";

        sensorsData.forEach(sensor => {
            renderWidget(sensor, container); // Add a widget for this sensor
        });

        // 3. ENTERPRISE LOGIC: Update the Main Hero Dashboard
        updateGlobalDashboard(sensorsData);

        // 4. Fetch the 24-Hour Farm Average Trend
        if (sensorsData.length > 0) {
            const chartResponse = await fetch(`${BASE_URL}/dashboard/chart`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const chartData = await chartResponse.json();
            renderChart(chartData);
        }

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}

// ==========================================
// ENTERPRISE GLOBAL DASHBOARD LOGIC
// ==========================================
function updateGlobalDashboard(sensors) {
    if (!sensors || sensors.length === 0) return;

    const now = new Date();
    const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;

    let activeSensors = [];
    let totalValidSensors = sensors.length;

    // 1. FILTER: Isolate only the fresh data (< 4 Hours)
    sensors.forEach(sensor => {
        const timestamp = sensor.last_reading_time || sensor.last_seen;
        if (timestamp) {
            const lastSeen = new Date(timestamp + (timestamp.endsWith('Z') ? '' : 'Z'));
            const diffMs = now - lastSeen;

            // Must be under 4 hours AND have a valid number
            if (diffMs <= FOUR_HOURS_MS && typeof sensor.moisture_pct === 'number') {
                activeSensors.push(sensor);
            }
        }
    });

    const activeCount = activeSensors.length;

    // 2. DOM Elements
    const statusEl = document.getElementById('global-status');
    const avgValueEl = document.getElementById('global-avg-value');
    const avgSymbolEl = document.getElementById('global-avg-symbol');
    const countEl = document.getElementById('global-sensor-count');

    // STATE C: TOTAL BLACKOUT (0 Sensors Active)
    if (activeCount === 0) {
        statusEl.innerText = "SYSTEM OFFLINE";
        statusEl.className = "text-sm font-bold tracking-widest uppercase mb-4 text-red-500 animate-pulse font-syne";

        avgValueEl.innerText = "--";
        avgValueEl.className = "text-[9rem] leading-none font-mono font-black text-slate-700 tracking-tighter transition-colors duration-500";
        avgSymbolEl.className = "text-4xl font-bold font-mono text-slate-700 transition-colors duration-500";

        countEl.innerText = `0/${totalValidSensors} SENSORS ACTIVE`;
        countEl.className = "text-[10px] font-bold text-red-500/70 font-mono mt-6 tracking-[0.2em] uppercase";

        // Change the top accent line to red
        document.getElementById('hero-accent').className = "absolute top-0 left-0 w-full h-1.5 bg-red-500 transition-colors duration-500";
        return;
    }

    // MATH: Calculate true average of active sensors
    const sum = activeSensors.reduce((acc, sensor) => acc + sensor.moisture_pct, 0);
    const trueAvg = Math.round(sum / activeCount);
    const isCriticalMoisture = trueAvg <= 20;

    // Apply the math to the UI (CHANGED TO ORANGE)
    avgValueEl.innerText = trueAvg;
    avgValueEl.className = `text-[9rem] leading-none font-mono font-black tracking-tighter transition-colors duration-500 ${isCriticalMoisture ? 'text-orange-500' : 'text-white'}`;
    avgSymbolEl.className = `text-4xl font-bold font-mono transition-colors duration-500 ${isCriticalMoisture ? 'text-orange-500' : 'text-slate-500'}`;

    // Change accent line color based on moisture
    document.getElementById('hero-accent').className = `absolute top-0 left-0 w-full h-1.5 transition-colors duration-500 ${isCriticalMoisture ? 'bg-orange-500' : 'bg-emerald-500'}`;

    // STATE B: PARTIAL OUTAGE (Degraded)
    if (activeCount < totalValidSensors) {
        statusEl.innerText = isCriticalMoisture ? "DEGRADED - LOW MOISTURE" : "SYSTEM DEGRADED";
        statusEl.className = "text-sm font-bold tracking-widest uppercase mb-4 text-yellow-500 font-syne";

        countEl.innerText = `${activeCount}/${totalValidSensors} SENSORS ACTIVE (BLIND SPOTS)`;
        countEl.className = "text-[10px] font-bold text-yellow-500 font-mono mt-6 tracking-[0.2em] uppercase";
    }
    // STATE A: 100% ONLINE (Healthy)
    else {
        // CHANGED TO ORANGE
        statusEl.innerText = isCriticalMoisture ? "LOW MOISTURE ALERT" : "SYSTEM HEALTHY";
        statusEl.className = `text-sm font-bold tracking-widest uppercase mb-4 font-syne ${isCriticalMoisture ? 'text-orange-500 animate-pulse' : 'text-emerald-500'}`;

        countEl.innerText = `${activeCount}/${totalValidSensors} SENSORS ACTIVE`;
        countEl.className = "text-[10px] font-bold text-slate-500 font-mono mt-6 tracking-[0.2em] uppercase";
    }
}

// ==========================================
// WIDGET RENDERING
// ==========================================
function renderWidget(sensor, container) {
    const moisture = sensor.moisture_pct;
    const timestamp = sensor.last_reading_time || sensor.last_seen || null;

    // CHANGED TO ORANGE
    let themeColor = moisture <= 20 ? "orange" : "emerald";
    let statusLabel = moisture <= 20 ? "LOW WATER" : "HEALTHY";

    let timeLabel = "---";
    let heartbeatClass = "text-slate-400";

    if (timestamp) {
        const lastSeenDate = new Date(timestamp + (timestamp.endsWith('Z') ? '' : 'Z'));
        const diffInMs = new Date() - lastSeenDate;
        const diffInMinutes = Math.floor(diffInMs / (1000 * 60));
        const diffInHours = Math.floor(diffInMinutes / 60);

        timeLabel = diffInHours >= 1 ? `${diffInHours}h ago` : `${diffInMinutes}m ago`;

        // RED REMAINS HERE FOR HARDWARE FAILURE
        if (diffInHours >= 12) {
            heartbeatClass = "text-red-500 font-black animate-pulse";
            statusLabel = "OFFLINE";
            themeColor = "slate"; // Optional: dim the widget if it's dead
        }
    }

    // ADDED ORANGE HEX
    const colorHex = themeColor === 'orange' ? '#f97316' : (themeColor === 'slate' ? '#475569' : '#10b981');

    container.innerHTML += `
        <div onclick="openModal('${sensor.device_eui}', '${sensor.name || "Field"}')" 
             class="custom-card rounded-2xl p-6 transition-all duration-500 cursor-pointer border border-white/5 hover:border-${themeColor}-500/40 relative overflow-hidden">
            
            <div class="flex justify-between items-start mb-6">
                <h4 class="font-syne text-white text-xl uppercase">${sensor.name || "Field"}</h4>
                <span class="px-2 py-0.5 text-[9px] font-black rounded-sm border border-${themeColor}-500/30 text-${themeColor}-500 tracking-widest uppercase">
                    ${statusLabel}
                </span>
            </div>

            <div class="relative flex items-center justify-center mb-4">
                <div class="flex items-baseline gap-1">
                    <span class="text-6xl font-mono tracking-tighter text-white">${moisture}</span>
                    <span class="text-xl font-bold text-slate-700 font-mono">%</span>
                </div>
            </div>

            <div class="w-full h-1 bg-white/5 rounded-full overflow-hidden mb-6">
                <div class="h-full bg-${themeColor}-500 shadow-[0_0_10px_${colorHex}]" style="width: ${moisture}%"></div>
            </div>

            <div class="grid grid-cols-3 pt-4 border-t border-white/5">
                <div>
                    <p class="text-[8px] text-slate-600 font-black uppercase font-syne">Temp</p>
                    <p class="text-xs font-bold text-slate-300 font-mono">${sensor.temperature_c}°C</p>
                </div>
                <div>
                    <p class="text-[8px] text-slate-600 font-black uppercase font-syne">Battery</p>
                    <p class="text-xs font-bold text-slate-300 font-mono">${sensor.battery_volts}V</p>
                </div>
                <div class="text-right">
                    <p class="text-[8px] text-slate-600 font-black uppercase font-syne">Last Seen</p>
                    <p class="text-xs font-bold font-mono ${heartbeatClass}">${timeLabel}</p>
                </div>
            </div>
        </div>
    `;
}

// ==========================================
// MAIN CHART & PAGINATION LOGIC
// ==========================================
let globalChartData = [];
let currentDayOffset = 0;
let mainChartInstance = null;

function renderChart(data) {
    globalChartData = data;
    currentDayOffset = 0;
    renderDay(currentDayOffset);
}

function renderDay(offset) {
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() - offset);

    const dayData = new Array(25).fill(null);
    let totalMoisture = 0;
    let count = 0;

    globalChartData.forEach(point => {
        const ptDate = new Date(point.timestamp + (point.timestamp.endsWith('Z') ? '' : 'Z'));

        if (ptDate.getDate() === targetDate.getDate() &&
            ptDate.getMonth() === targetDate.getMonth() &&
            ptDate.getFullYear() === targetDate.getFullYear()) {

            const hour = ptDate.getHours();
            dayData[hour] = point.avg_moisture;
            totalMoisture += point.avg_moisture;
            count++;
        }

        const nextDay = new Date(targetDate);
        nextDay.setDate(targetDate.getDate() + 1);

        if (ptDate.getDate() === nextDay.getDate() &&
            ptDate.getHours() === 0) {
            dayData[24] = point.avg_moisture;
        }
    });

    if (dayData[24] === null && dayData[23] !== null) {
        dayData[24] = dayData[23];
    }

    const avgText = count > 0 ? Math.round(totalMoisture / count) + "%" : "--%";
    document.getElementById('chart-daily-avg').innerText = avgText;

    const labelEl = document.getElementById('chart-date-label');
    if (offset === 0) labelEl.innerText = "Today";
    else if (offset === 1) labelEl.innerText = "Yesterday";
    else labelEl.innerText = targetDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

    document.getElementById('btn-next-day').style.display = offset === 0 ? 'none' : 'block';
    document.getElementById('btn-prev-day').style.display = offset >= 2 ? 'none' : 'block';

    const labels = ['12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM', '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM', '12 AM'];

    if (mainChartInstance) mainChartInstance.destroy();
    const canvas = document.getElementById('mainChart');
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.2)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0)');

    const currentHour = new Date().getHours();

    mainChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Moisture (%)',
                    data: dayData,
                    borderColor: '#10b981',
                    borderWidth: 4,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    spanGaps: true,
                    pointRadius: 0,
                    order: 0
                },
                {
                    label: 'Threshold',
                    data: new Array(25).fill(20),
                    borderColor: 'rgba(239, 68, 68, 0.4)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false,
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 25,
                    bottom: 10,
                    left: 10,
                    right: 10
                }
            },
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#11191f',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Inter', size: 10, weight: 'bold' },
                    bodyFont: { family: 'JetBrains Mono', size: 14, weight: '900' },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false,
                    filter: (item) => item.dataset.label !== 'Threshold',
                    callbacks: {
                        label: (context) => `${context.parsed.y}% MOISTURE`
                    }
                }
            },
            scales: {
                y: {
                    min: 0, max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    ticks: { color: '#475569', font: { family: 'JetBrains Mono', size: 10, weight: '600' } }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        color: '#475569',
                        font: { family: 'JetBrains Mono', size: 10, weight: '600' },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12
                    }
                }
            }
        },
        plugins: [{
            id: 'verticalLine',
            afterDraw: (chart) => {
                if (offset === 0) {
                    const xCoor = chart.scales.x.getPixelForValue(labels[currentHour]);
                    ctx.save();
                    ctx.beginPath();
                    ctx.setLineDash([5, 5]);
                    ctx.moveTo(xCoor, chart.scales.y.top);
                    ctx.lineTo(xCoor, chart.scales.y.bottom);
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                    ctx.stroke();
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
                    ctx.font = 'bold 10px Inter';
                    ctx.fillText('NOW', xCoor - 11.5, chart.scales.y.top + 5);
                    ctx.restore();
                }
            }
        }]
    });
}

document.getElementById('btn-prev-day').addEventListener('click', () => {
    if (currentDayOffset < 2) {
        currentDayOffset++;
        renderDay(currentDayOffset);
    }
});

document.getElementById('btn-next-day').addEventListener('click', () => {
    if (currentDayOffset > 0) {
        currentDayOffset--;
        renderDay(currentDayOffset);
    }
});

// ==========================================
// ENTERPRISE REAL-TIME WEBSOCKET CONNECTION
// ==========================================
function connectWebSocket() {
    const isProd = BASE_URL.includes('onrender.com');
    const wsProtocol = isProd ? 'wss:' : 'ws:';
    const domain = BASE_URL.split('/')[2];
    const wsUrl = `${wsProtocol}//${domain}/ws`;

    const socket = new WebSocket(wsUrl);

    socket.onopen = () => console.log("🟢 Live Pipeline Connected!");
    socket.onmessage = (event) => {
        if (event.data === "NEW_DATA") {
            console.log("⚡ Auto-updating dashboard...");
            fetchAllData();
        }
    };
    socket.onclose = () => setTimeout(connectWebSocket, 5000);
}

window.onload = () => {
    fetchAllData();
    connectWebSocket();
};

// ==========================================
// SENSOR DETAIL MODAL LOGIC (Paginated)
// ==========================================
let modalChartInstance = null;
let globalModalData = [];
let currentModalOffset = 0;

async function openModal(device_eui, sensorName) {
    const modal = document.getElementById('sensorModal');
    modal.classList.remove('hidden');

    document.getElementById('modalTitle').innerText = sensorName;
    document.getElementById('modalSubtitle').innerText = device_eui;

    try {
        const response = await fetch(`${BASE_URL}/sensors/${device_eui}/readings`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Failed to fetch sensor details");

        globalModalData = await response.json();
        currentModalOffset = 0;

        setTimeout(() => {
            renderModalDay(currentModalOffset);
        }, 100);

    } catch (error) {
        console.error("Modal fetch error:", error);
    }
}

function closeModal() {
    document.getElementById('sensorModal').classList.add('hidden');
    if (modalChartInstance) {
        modalChartInstance.destroy();
        modalChartInstance = null;
    }
}

function renderModalDay(offset) {
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() - offset);

    const dayData = new Array(25).fill(null);
    const hourlySums = new Array(25).fill(0);
    const hourlyCounts = new Array(25).fill(0);
    let totalMoisture = 0;
    let count = 0;

    globalModalData.forEach(point => {
        const ptDate = new Date(point.timestamp + (point.timestamp.endsWith('Z') ? '' : 'Z'));

        if (ptDate.getDate() === targetDate.getDate() &&
            ptDate.getMonth() === targetDate.getMonth() &&
            ptDate.getFullYear() === targetDate.getFullYear()) {

            const hour = ptDate.getHours();
            hourlySums[hour] += point.moisture_pct;
            hourlyCounts[hour]++;
            totalMoisture += point.moisture_pct;
            count++;
        }

        const nextDay = new Date(targetDate);
        nextDay.setDate(targetDate.getDate() + 1);

        if (ptDate.getDate() === nextDay.getDate() &&
            ptDate.getMonth() === nextDay.getMonth() &&
            ptDate.getHours() === 0) {
            dayData[24] = point.moisture_pct;
        }
    });

    for (let i = 0; i < 24; i++) {
        if (hourlyCounts[i] > 0) {
            dayData[i] = hourlySums[i] / hourlyCounts[i];
        }
    }

    if (dayData[24] === null && dayData[23] !== null) {
        dayData[24] = dayData[23];
    }

    // ==========================================
    // ENTERPRISE COLOR LOGIC FOR MODALS
    // ==========================================
    const hasData = count > 0; // NEW: Explicitly check if we have data
    const trueAvg = hasData ? Math.round(totalMoisture / count) : null;
    const avgText = hasData ? trueAvg + "%" : "--";

    let themeColor = "emerald";
    let hexColor = "#10b981"; // Emerald Default

    if (trueAvg === null) {
        themeColor = "red";
        hexColor = "#ef4444"; // Red (Total Blackout / No Data for this day)
    } else if (trueAvg <= 20) {
        themeColor = "orange";
        hexColor = "#f97316"; // Orange (Low Moisture)
    }

    // Update DOM Text Colors
    const avgEl = document.getElementById('modal-daily-avg');
    avgEl.innerText = avgText;
    avgEl.className = `text-5xl font-mono font-black tracking-tighter transition-colors duration-500 ${trueAvg !== null && trueAvg <= 20 ? 'text-orange-500' : 'text-white'}`;

    const labelEl = document.getElementById('modal-date-label');
    if (offset === 0) labelEl.innerText = "Today";
    else if (offset === 1) labelEl.innerText = "Yesterday";
    else labelEl.innerText = targetDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

    // Apply dynamic color to the date label
    labelEl.className = `text-xs font-bold uppercase tracking-widest mb-1 font-syne text-${themeColor}-500`;

    document.getElementById('btn-modal-next').style.display = offset === 0 ? 'none' : 'block';
    document.getElementById('btn-modal-prev').style.display = offset >= 2 ? 'none' : 'block';

    const labels = ['12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM', '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM', '12 AM'];

    const ctx = document.getElementById('modalChart');
    if (!ctx) return;

    if (modalChartInstance) modalChartInstance.destroy();
    const context = ctx.getContext('2d');

    // Helper: Convert Hex to RGBA for smooth Chart.js gradients
    const hexToRgba = (hex, alpha) => {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    // Apply the dynamic color to the gradient
    const dynamicGradient = context.createLinearGradient(0, 0, 0, 400);
    dynamicGradient.addColorStop(0, hexToRgba(hexColor, 0.2));
    dynamicGradient.addColorStop(1, hexToRgba(hexColor, 0));

    const currentHour = new Date().getHours();

    modalChartInstance = new Chart(context, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moisture (%)',
                data: dayData,
                borderColor: hexColor, // Dynamic Line Color
                borderWidth: 4,
                backgroundColor: dynamicGradient, // Dynamic Gradient
                fill: true,
                tension: 0.4,
                spanGaps: true,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: hexColor,
                pointBorderColor: hexColor,
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2,
                pointBackgroundColor: '#0B1215'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 25, bottom: 10, left: 10, right: 10 }
            },
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#11191f',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Inter', size: 10, weight: 'bold' },
                    bodyFont: { family: 'DM Mono', size: 14, weight: '900' },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: function (context) {
                            return `${context.parsed.y}% MOISTURE`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    min: 0, max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#475569', font: { family: 'DM Mono', size: 10 } }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        maxTicksLimit: 12,
                        maxRotation: 0,
                        autoSkip: true,
                        color: '#475569',
                        font: { family: 'DM Mono', size: 10 }
                    }
                }
            }
        },
        plugins: [
            // Plugin 1: The "NOW" Line
            {
                id: 'verticalLine',
                afterDraw: (chart) => {
                    if (offset === 0 && chart.scales.x && hasData) { // Only draw NOW line if there is data
                        const xCoor = chart.scales.x.getPixelForValue(labels[currentHour]);
                        context.save();
                        context.beginPath();
                        context.setLineDash([5, 5]);
                        context.moveTo(xCoor, chart.scales.y.top);
                        context.lineTo(xCoor, chart.scales.y.bottom);
                        context.lineWidth = 2;
                        context.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                        context.stroke();

                        context.fillStyle = 'rgba(255, 255, 255, 0.4)';
                        context.font = 'bold 10px Inter';
                        context.fillText('NOW', xCoor - 11, chart.scales.y.top + 8);
                        context.restore();
                    }
                }
            },
            // Plugin 2: NEW! The "No Data" Watermark
            {
                id: 'noDataWatermark',
                afterDraw: (chart) => {
                    if (!hasData) {
                        const width = chart.width;
                        const height = chart.height;

                        context.save();
                        context.textAlign = 'center';
                        context.textBaseline = 'middle';

                        // Main Warning Text
                        context.font = '900 18px Inter';
                        context.fillStyle = 'rgba(239, 68, 68, 0.5)'; // Faded Red to match the theme
                        context.fillText('NO DATA RECORDED', width / 2, height / 2);

                        // Subtitle
                        context.font = 'bold 10px DM Mono';
                        context.fillStyle = 'rgba(239, 68, 68, 0.3)';
                        context.fillText('SENSOR OFFLINE OR UNREACHABLE', width / 2, (height / 2) + 22);

                        context.restore();
                    }
                }
            }
        ]
    });
}

document.getElementById('btn-modal-prev').addEventListener('click', () => {
    if (currentModalOffset < 2) {
        currentModalOffset++;
        renderModalDay(currentModalOffset);
    }
});

document.getElementById('btn-modal-next').addEventListener('click', () => {
    if (currentModalOffset > 0) {
        currentModalOffset--;
        renderModalDay(currentModalOffset);
    }
});