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

        // 2. Clear the "Loading" text and prepare the math
        const container = document.getElementById('sensor-widgets-container');
        container.innerHTML = "";
        let totalMoisture = 0;

        // 3. Loop through every sensor in the database
        sensorsData.forEach(sensor => {
            totalMoisture += sensor.moisture_pct;
            renderWidget(sensor, container); // Add a widget for this sensor
        });

        // 4. Calculate the real Farm-Wide Average
        if (sensorsData.length > 0) {
            const avg = totalMoisture / sensorsData.length;
            updateAverage(avg);

            // 5. Fetch the 24-Hour Farm Average Trend
            const chartResponse = await fetch(`${BASE_URL}/dashboard/chart`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const chartData = await chartResponse.json();

            // Pass the perfectly formatted 24-hour data straight to the chart!
            renderChart(chartData);
        }

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}

function updateAverage(value) {
    const element = document.getElementById('farm-avg');
    const badge = document.getElementById('hero-status-badge');
    const roundedValue = Math.round(value);

    element.innerText = roundedValue;
    element.className = "font-mono tracking-tighter ";

    if (roundedValue <= 20) {
        element.classList.add('text-red-500');
        badge.className = "px-3 py-1 text-[10px] font-black rounded-full uppercase tracking-widest bg-red-500/10 text-red-500 animate-pulse";
        badge.innerText = "CRITICAL: BELOW 20%";
    } else {
        element.classList.add('text-emerald-500');
        badge.className = "px-3 py-1 text-[10px] font-black rounded-full uppercase tracking-widest bg-emerald-500/10 text-emerald-500";
        badge.innerText = "SYSTEM HEALTHY";
    }
}

function renderWidget(sensor, container) {
    const moisture = sensor.moisture_pct;
    const timestamp = sensor.last_reading_time || sensor.last_seen || null;

    // Status Logic (Back to 20% Threshold)
    let themeColor = moisture <= 20 ? "red" : "emerald";
    let statusLabel = moisture <= 20 ? "CRITICAL" : "HEALTHY";

    let timeLabel = "---";
    let isOffline = false;
    if (timestamp) {
        const tsString = timestamp.endsWith('Z') ? timestamp : timestamp + 'Z';
        const diff = Math.floor((new Date() - new Date(tsString)) / (1000 * 60));

        if (diff < 1) timeLabel = "Just now";
        else if (diff < 60) timeLabel = `${diff}m ago`;
        else if (diff < 1440) timeLabel = `${Math.floor(diff / 60)}h ago`;
        else timeLabel = `${Math.floor(diff / 1440)}d ago`;

        // Offline detection: no data for 60+ minutes
        if (diff >= 60) {
            isOffline = true;
            // Only override to OFFLINE if not already CRITICAL (moisture alarm takes priority)
            if (statusLabel !== "CRITICAL") {
                themeColor = "amber";
                statusLabel = "OFFLINE";
            }
        }
    }

    const colorHex = themeColor === 'red' ? '#ef4444' : themeColor === 'amber' ? '#f59e0b' : '#10b981';

    container.innerHTML += `
        <div onclick="openModal('${sensor.device_eui}', '${sensor.name || "Field"}')" 
             class="custom-card rounded-2xl p-6 transition-all duration-500 cursor-pointer border border-white/5 hover:border-${themeColor}-500/40 relative overflow-hidden">
            
            <div class="flex justify-between items-start mb-6">
                <h4 class="text-white text-xl font-bold uppercase">${sensor.name || "Field"}</h4>
                <span class="px-2 py-0.5 text-[9px] font-black rounded-sm border border-${themeColor}-500/30 text-${themeColor}-500 tracking-widest">
                    ${statusLabel}
                </span>
            </div>

            <div class="mb-4">
                <div class="flex items-baseline gap-1">
                    <span class="text-6xl font-mono tracking-tighter text-white">${moisture}</span>
                    <span class="text-xl font-bold text-slate-700">%</span>
                </div>
            </div>

            <div class="w-full h-1 bg-white/5 rounded-full overflow-hidden mb-6">
                <div class="h-full bg-${themeColor}-500 shadow-[0_0_10px_${colorHex}]" style="width: ${moisture}%"></div>
            </div>

            <div class="grid grid-cols-3 pt-4 border-t border-white/5">
                <div>
                    <p class="text-[8px] text-slate-600 font-black uppercase">Temp</p>
                    <p class="text-xs font-bold text-slate-300 font-mono">${sensor.temperature_c}°C</p>
                </div>
                <div>
                    <p class="text-[8px] text-slate-600 font-black uppercase">Battery</p>
                    <p class="text-xs font-bold text-slate-300 font-mono">${sensor.battery_volts}V</p>
                </div>
                <div class="text-right">
                    <p class="text-[8px] text-slate-600 font-black uppercase">Last Seen</p>
                    <p class="text-xs font-bold text-slate-400 font-mono">${timeLabel}</p>
                </div>
            </div>
        </div>
    `;
}

// --- MAIN CHART & PAGINATION LOGIC ---
let globalChartData = [];
let currentDayOffset = 0; // 0 = Today, 1 = Yesterday, 2 = Two days ago
let mainChartInstance = null;

// This replaces the old renderChart. It saves the data globally, then draws "Today"
function renderChart(data) {
    globalChartData = data;
    currentDayOffset = 0; // Always start on Today after a refresh
    renderDay(currentDayOffset);
}

function renderDay(offset) {
    // 1. Figure out which calendar day we are looking at
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() - offset);

    // 2. Create a blank 24-hour array (12 AM to 11 PM) filled with 'null'
    const dayData = new Array(25).fill(null);
    let totalMoisture = 0;
    let count = 0;

    // 3. Loop through all 72 hours of data from the backend. 
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
    });

    // 4. Update the Daily Average Text (Updated to match Slate colors)
    const avgText = count > 0 ? Math.round(totalMoisture / count) + "%" : "--%";
    document.getElementById('chart-daily-avg').innerText = avgText;

    // 5. Update the Emerald Date Label text
    const labelEl = document.getElementById('chart-date-label');
    if (offset === 0) labelEl.innerText = "Today";
    else if (offset === 1) labelEl.innerText = "Yesterday";
    else labelEl.innerText = targetDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

    // 6. Show or Hide the Left/Right arrows based on where we are
    document.getElementById('btn-next-day').style.display = offset === 0 ? 'none' : 'block';
    document.getElementById('btn-prev-day').style.display = offset >= 2 ? 'none' : 'block';

    // 7. Draw the fixed 24-hour chart with Premium Emerald Styling
    const labels = ['12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM', '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM', '12 AM'];

    if (mainChartInstance) mainChartInstance.destroy();
    const ctx = document.getElementById('mainChart').getContext('2d');

    // Create a subtle gradient for the fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.2)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0)');

    mainChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moisture (%)',
                data: dayData,
                borderColor: '#10b981', // High-contrast Emerald
                borderWidth: 4,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4,
                spanGaps: true,
                pointBackgroundColor: '#0B1215', // Matches background
                pointBorderColor: '#10b981',
                pointBorderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#10b981',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#11191f', // Deepest Slate
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Inter', size: 10, weight: 'bold' },
                    bodyFont: { family: 'JetBrains Mono', size: 14, weight: '900' },
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
                    min: 0,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)', // Very subtle white grid
                        drawBorder: false
                    },
                    ticks: {
                        color: '#475569', // Slate 500
                        font: { family: 'JetBrains Mono', size: 10, weight: '600' }
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        maxTicksLimit: 7,
                        maxRotation: 0,
                        color: '#475569', // Slate 500
                        font: { family: 'JetBrains Mono', size: 10, weight: '600' }
                    }
                }
            }
        }
    });
}

// --- ARROW BUTTON EVENT LISTENERS ---
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

// Initial Load
// ==========================================
// ENTERPRISE REAL-TIME WEBSOCKET CONNECTION
// ==========================================
function connectWebSocket() {
    // Force WSS for Render, WS for local
    const isProd = BASE_URL.includes('onrender.com');
    const wsProtocol = isProd ? 'wss:' : 'ws:';

    // Get the clean domain name (e.g., farmer-alert-api.onrender.com)
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

// Initial Load
window.onload = () => {
    fetchAllData();
    connectWebSocket();
};

// ==========================================
// SENSOR DETAIL MODAL LOGIC (Paginated)
// ==========================================
let modalChartInstance = null;
let globalModalData = [];
let currentModalOffset = 0; // 0 = Today, 1 = Yesterday

async function openModal(device_eui, sensorName) {
    // 1. Show the modal first
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

        // 2. THE FIX: Wait 100ms for the browser to "render" the modal 
        // before we try to draw the chart inside it.
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

    // Arrays to hold the math for grouping raw readings into hourly averages
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
    });

    // Calculate the final average for each hour
    const dayData = new Array(25).fill(null);
    for (let i = 0; i < 25; i++) {
        if (hourlyCounts[i] > 0) {
            dayData[i] = hourlySums[i] / hourlyCounts[i];
        }
    }

    // Update Modal UI Labels
    const avgText = count > 0 ? Math.round(totalMoisture / count) + "%" : "--%";
    document.getElementById('modal-daily-avg').innerText = avgText;

    const labelEl = document.getElementById('modal-date-label');
    if (offset === 0) labelEl.innerText = "Today";
    else if (offset === 1) labelEl.innerText = "Yesterday";
    else labelEl.innerText = targetDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

    // Arrow Visibility
    document.getElementById('btn-modal-next').style.display = offset === 0 ? 'none' : 'block';
    document.getElementById('btn-modal-prev').style.display = offset >= 2 ? 'none' : 'block';

    // Draw the Modal Chart
    const labels = ['12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM', '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM', '12 AM'];

    const ctx = document.getElementById('modalChart');
    if (!ctx) return; // Safety check

    if (modalChartInstance) modalChartInstance.destroy();

    const context = ctx.getContext('2d');
    const blueGradient = context.createLinearGradient(0, 0, 0, 400);
    blueGradient.addColorStop(0, 'rgba(59, 130, 246, 0.2)');
    blueGradient.addColorStop(1, 'rgba(59, 130, 246, 0)');

    modalChartInstance = new Chart(context, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moisture (%)',
                data: dayData,
                borderColor: '#3b82f6',
                borderWidth: 4,
                backgroundColor: blueGradient,
                fill: true,
                tension: 0.4,
                spanGaps: true,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#3b82f6',
                pointBorderColor: '#3b82f6',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2,
                pointBackgroundColor: '#0B1215'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
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
                        maxTicksLimit: 7,
                        maxRotation: 0,
                        color: '#475569',
                        font: { family: 'DM Mono', size: 10 }
                    }
                }
            }
        }
    });
}

// Modal Arrow Button Listeners
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