// Point this to your local FastAPI server and the specific sensor we are testing
const API_URL = "http://127.0.0.1:8000/api/sensors/2CF7F1C042500001/readings";
let moistureChart = null;

// The asynchronous function to grab data from the backend
async function fetchSensorData() {
    try {
        const response = await fetch(API_URL);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error("Could not fetch data from API:", error);
        document.getElementById('moisture').innerText = "Err";
    }
}

// The function to parse the JSON and update the HTML elements
function updateDashboard(data) {
    // If the database is empty, do nothing
    if (data.length === 0) return;

    // 1. Update the Status Cards
    // Our API returns the newest reading first (index 0)
    const latestReading = data[0];
    document.getElementById('moisture').innerText = latestReading.moisture_pct + "%";
    document.getElementById('temp').innerText = latestReading.temperature_c + "°C";
    document.getElementById('battery').innerText = latestReading.battery_volts + "V";

    // 2. Prepare Data for the Chart
    // We want the chart to read left-to-right (oldest to newest), so we reverse the array
    const chronologicalData = data.slice().reverse();

    // Extract timestamps for the X-axis
    const labels = chronologicalData.map(reading => {
        // Add 'Z' to tell JavaScript this time is in UTC, so it converts to your local time zone
        const date = new Date(reading.timestamp + "Z");
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

    // Extract moisture percentages for the Y-axis
    const moistureValues = chronologicalData.map(reading => reading.moisture_pct);

    // 3. Draw the Chart
    renderChart(labels, moistureValues);
}

// The function to configure and draw Chart.js
function renderChart(labels, dataPoints) {
    const ctx = document.getElementById('moistureChart').getContext('2d');

    // If a chart already exists, destroy it before drawing a new one to prevent glitching
    if (moistureChart) {
        moistureChart.destroy();
    }

    // 
    moistureChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Soil Moisture (%)',
                data: dataPoints,
                borderColor: 'rgba(59, 130, 246, 1)', // Tailwind Blue-500
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4, // Gives the line a smooth curve instead of sharp angles
                pointRadius: 4,
                pointBackgroundColor: 'rgba(59, 130, 246, 1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Moisture Percentage' }
                }
            },
            plugins: {
                legend: { display: false } // Hides the top legend to save space
            }
        }
    });
}

// Run the fetch function immediately when the page loads
window.onload = fetchSensorData;