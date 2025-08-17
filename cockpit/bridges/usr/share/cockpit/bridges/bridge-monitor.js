let autoRefreshInterval = null;
let isAutoRefresh = false;

function showError(message) {
    const errorContainer = document.getElementById('error-container');
    errorContainer.innerHTML = '<div class="error-message">' + message + '</div>';
}

function clearError() {
    document.getElementById('error-container').innerHTML = '';
}

function showLoading() {
    document.getElementById('loading').style.display = 'block';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    return date.toLocaleString();
}

function createBridgeCard(bridge) {
    const statusClass = bridge.status === 'up' ? 'up status-up' : 'down status-down';
    const stpClass = bridge.stp_state === 'enabled' ? 'stp-enabled' : 'stp-disabled';
    
    const interfacesList = bridge.interfaces.length > 0 
        ? bridge.interfaces.slice(0, 5).join(', ') + (bridge.interfaces.length > 5 ? '...' : '')
        : 'None';
    
    return '<div class="bridge-card ' + bridge.status + '">' +
        '<div class="bridge-header">' +
            '<div class="bridge-name">' + bridge.name + '</div>' +
            '<div class="bridge-status ' + statusClass + '">' + bridge.status.toUpperCase() + '</div>' +
        '</div>' +
        '<div class="bridge-metrics">' +
            '<div class="metric-row">' +
                '<div class="metric rx-metric">' +
                    '<div class="metric-label">RX</div>' +
                    '<div class="metric-value">' + formatBytes(bridge.rx_bytes) + '</div>' +
                    '<div class="metric-subtitle">' + bridge.rx_packets.toLocaleString() + ' packets</div>' +
                '</div>' +
                '<div class="metric tx-metric">' +
                    '<div class="metric-label">TX</div>' +
                    '<div class="metric-value">' + formatBytes(bridge.tx_bytes) + '</div>' +
                    '<div class="metric-subtitle">' + bridge.tx_packets.toLocaleString() + ' packets</div>' +
                '</div>' +
            '</div>' +
        '</div>' +
        '<div class="bridge-details">' +
            '<div class="detail-row">' +
                '<div class="detail-label">Interfaces:</div>' +
                '<div class="detail-value">' + interfacesList + '</div>' +
            '</div>' +
            '<div class="detail-row">' +
                '<div class="detail-label">STP State:</div>' +
                '<div class="detail-value ' + stpClass + '">' + bridge.stp_state + '</div>' +
            '</div>' +
            '<div class="detail-row">' +
                '<div class="detail-label">Errors:</div>' +
                '<div class="detail-value">RX: ' + bridge.rx_errors + ', TX: ' + bridge.tx_errors + '</div>' +
            '</div>' +
            '<div class="detail-row">' +
                '<div class="detail-label">Dropped:</div>' +
                '<div class="detail-value">RX: ' + bridge.rx_dropped + ', TX: ' + bridge.tx_dropped + '</div>' +
            '</div>' +
        '</div>' +
    '</div>';
}

function updateBridgeDisplay(data) {
    const container = document.getElementById('bridge-container');
    const lastUpdatedDiv = document.getElementById('last-updated');
    
    if (!data || !data.bridges) {
        container.innerHTML = '<div class="no-bridges">No bridges found</div>';
        return;
    }

    if (data.bridges.length === 0) {
        container.innerHTML = '<div class="no-bridges">No bridges found on this system</div>';
    } else {
        const bridgeCards = data.bridges.map(function(bridge) { return createBridgeCard(bridge); }).join('');
        container.innerHTML = '<div class="bridge-grid">' + bridgeCards + '</div>';
    }

    lastUpdatedDiv.textContent = 'Last updated: ' + formatTimestamp(data.timestamp) + ' (' + data.bridge_count + ' bridges found)';
}

function refreshData() {
    clearError();
    showLoading();

    cockpit.spawn(['/usr/bin/python3', '/usr/local/bin/bridge_monitor.py', '--json'])
        .done(function(data) {
            hideLoading();
            try {
                const jsonData = JSON.parse(data);
                updateBridgeDisplay(jsonData);
            } catch (e) {
                showError('Failed to parse bridge data: ' + e.message);
            }
        })
        .fail(function(error) {
            hideLoading();
            showError('Failed to retrieve bridge data: ' + error.message);
        });
}

function toggleAutoRefresh() {
    const icon = document.getElementById('auto-refresh-icon');
    const text = document.getElementById('auto-refresh-text');
    
    if (isAutoRefresh) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        isAutoRefresh = false;
        icon.className = 'fa fa-play';
        text.textContent = 'Start Auto-refresh';
    } else {
        autoRefreshInterval = setInterval(refreshData, 30000);
        isAutoRefresh = true;
        icon.className = 'fa fa-pause';
        text.textContent = 'Stop Auto-refresh';
        refreshData();
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('refresh-btn').addEventListener('click', refreshData);
    document.getElementById('auto-refresh-btn').addEventListener('click', toggleAutoRefresh);
    
    refreshData();
});