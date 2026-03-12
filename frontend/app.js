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
    element.innerText = Math.round(value);

    // Remove old colors just in case it updates
    element.classList.remove('text-red-600', 'text-gray-800');

    // Change color based on health (20% threshold)
    if (value <= 20) {
        element.classList.add('text-red-600');
    } else {
        element.classList.add('text-gray-800');
    }
}

function renderWidget(sensor, container) {
    const isCritical = sensor.moisture_pct <= 20;

    // Added cursor-pointer, hover:-translate-y-1, and onclick!
    container.innerHTML += `
        <div onclick="openModal('${sensor.device_eui}', '${sensor.name || "Field Sensor"}')" class="bg-white p-5 rounded-xl border border-gray-100 shadow-sm mb-4 hover:shadow-lg transition cursor-pointer transform hover:-translate-y-1">
            <div class="flex justify-between items-start mb-4">
                <div>
                    <h4 class="font-bold text-gray-800 text-sm">${sensor.name || "Field Sensor"}</h4>
                    <p class="text-[10px] text-gray-400 font-mono">${sensor.device_eui}</p>
                </div>
                <span class="px-2 py-1 text-[10px] font-bold rounded ${isCritical ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}">
                    ${isCritical ? 'CRITICAL' : 'ONLINE'}
                </span>
            </div>
            <div class="grid grid-cols-3 gap-2">
                <div class="text-center">
                    <p class="text-[10px] text-gray-400 uppercase">Moisture</p>
                    <p class="text-lg font-bold ${isCritical ? 'text-red-600' : 'text-blue-600'}">${sensor.moisture_pct}%</p>
                </div>
                <div class="text-center">
                    <p class="text-[10px] text-gray-400 uppercase">Temp</p>
                    <p class="text-lg font-bold text-gray-700">${sensor.temperature_c}°C</p>
                </div>
                <div class="text-center">
                    <p class="text-[10px] text-gray-400 uppercase">Battery</p>
                    <p class="text-lg font-bold text-gray-700">${sensor.battery_volts}V</p>
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

// The engine that filters data for a specific day and draws the iOS-style chart
function renderDay(offset) {
    // 1. Figure out which calendar day we are looking at
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() - offset);

    // 2. Create a blank 24-hour array (12 AM to 11 PM) filled with 'null'
    const dayData = new Array(25).fill(null);
    let totalMoisture = 0;
    let count = 0;

    // 3. Loop through all 72 hours of data from the backend. 
    // If a point belongs to our target day, drop it into the correct hour slot!
    globalChartData.forEach(point => {
        const ptDate = new Date(point.timestamp);
        if (ptDate.getDate() === targetDate.getDate() &&
            ptDate.getMonth() === targetDate.getMonth() &&
            ptDate.getFullYear() === targetDate.getFullYear()) {

            const hour = ptDate.getHours();
            dayData[hour] = point.avg_moisture;
            totalMoisture += point.avg_moisture;
            count++;
        }
    });

    // 4. Update the Daily Average Text in the top right
    const avgText = count > 0 ? Math.round(totalMoisture / count) + "%" : "--%";
    document.getElementById('chart-daily-avg').innerText = avgText;

    // 5. Update the Green Date Label text
    const labelEl = document.getElementById('chart-date-label');
    if (offset === 0) labelEl.innerText = "Today";
    else if (offset === 1) labelEl.innerText = "Yesterday";
    else labelEl.innerText = targetDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

    // 6. Show or Hide the Left/Right arrows based on where we are
    document.getElementById('btn-next-day').style.display = offset === 0 ? 'none' : 'block';
    document.getElementById('btn-prev-day').style.display = offset >= 2 ? 'none' : 'block';

    // 7. Draw the fixed 24-hour chart
    // 7. Draw the fixed 24-hour chart
    const labels = ['12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM', '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM', '12 AM'];

    if (mainChartInstance) mainChartInstance.destroy();
    const ctx = document.getElementById('mainChart').getContext('2d');

    mainChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moisture (%)',
                data: dayData,
                borderColor: '#16a34a',
                backgroundColor: 'rgba(22, 163, 74, 0.05)',
                fill: true,
                tension: 0.4,
                spanGaps: true, // MAGIC! This connects the line even if some hours are blank
                pointBackgroundColor: '#fff',
                pointBorderColor: '#16a34a',
                pointBorderWidth: 2,
                pointRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { min: 0, max: 100 },
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 9, maxRotation: 0 }
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
    // Dynamically figure out if we are on localhost or Render, and swap http for ws
    const wsProtocol = BASE_URL.includes('https') ? 'wss:' : 'ws:';
    const wsHost = BASE_URL.replace('http://', '').replace('https://', '').replace('/api', '');
    const wsUrl = `${wsProtocol}//${wsHost}/ws`;

    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("🟢 Enterprise WebSocket Pipeline Connected!");
    };

    socket.onmessage = (event) => {
        if (event.data === "NEW_DATA") {
            console.log("⚡ New data detected! Updating dashboard silently...");
            // We got the ping! Fetch the fresh data without reloading the page.
            fetchAllData();
        }
    };

    socket.onclose = () => {
        console.log("🔴 Pipeline disconnected. Reconnecting in 5 seconds...");
        setTimeout(connectWebSocket, 5000);
    };
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
    document.getElementById('sensorModal').classList.remove('hidden');
    document.getElementById('modalTitle').innerText = sensorName;
    document.getElementById('modalSubtitle').innerText = device_eui;

    try {
        const response = await fetch(`${BASE_URL}/sensors/${device_eui}/readings`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Failed to fetch sensor details");

        globalModalData = await response.json();
        currentModalOffset = 0; // Reset to Today
        renderModalDay(currentModalOffset);

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
        const ptDate = new Date(point.timestamp);
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

    if (modalChartInstance) modalChartInstance.destroy();
    const ctx = document.getElementById('modalChart').getContext('2d');

    modalChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moisture (%)',
                data: dayData,
                borderColor: '#2563eb', // Blue line for individual sensors
                backgroundColor: 'rgba(37, 99, 235, 0.05)',
                fill: true,
                tension: 0.4,
                spanGaps: true,
                pointBackgroundColor: '#fff',
                pointBorderColor: '#2563eb',
                pointBorderWidth: 2,
                pointRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { min: 0, max: 100 },
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 9, maxRotation: 0 }
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