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

function formatUptime(uptime) {
    if (!uptime || uptime === '0m') return 'Just started';
    return uptime;
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    return date.toLocaleString();
}

function createVMCard(vm) {
    const statusClass = vm.status === 'running' ? 'running status-running' : 'stopped status-stopped';
    
    return '<div class="vm-card ' + vm.status + '">' +
        '<div class="vm-header">' +
            '<div class="vm-name">' + vm.name + '</div>' +
            '<div class="vm-status ' + statusClass + '">' + vm.status.toUpperCase() + '</div>' +
        '</div>' +
        '<div class="vm-metrics">' +
            '<div class="metric">' +
                '<div class="metric-value">' + (vm.cpu_percent || 0) + '%</div>' +
                '<div class="metric-label">CPU</div>' +
            '</div>' +
            '<div class="metric">' +
                '<div class="metric-value">' + (vm.memory_mb || 0) + '</div>' +
                '<div class="metric-label">Memory (MB)</div>' +
            '</div>' +
        '</div>' +
        '<div class="vm-details">' +
            '<div><strong>PID:</strong> ' + (vm.pid || 'N/A') + '</div>' +
            '<div><strong>Uptime:</strong> ' + formatUptime(vm.uptime) + '</div>' +
            '<div><strong>Network:</strong> ' + (vm.network_interfaces || 'default') + '</div>' +
            '<div><strong>Type:</strong> ' + (vm.type || 'nexus9000v') + '</div>' +
        '</div>' +
    '</div>';
}

function updateVMDisplay(data) {
    const container = document.getElementById('vm-container');
    const lastUpdatedDiv = document.getElementById('last-updated');
    
    if (!data || !data.vms) {
        container.innerHTML = '<div class="no-vms">No Nexus 9000v VMs found</div>';
        return;
    }

    if (data.vms.length === 0) {
        container.innerHTML = '<div class="no-vms">No Nexus 9000v VMs are currently running</div>';
    } else {
        const vmCards = data.vms.map(function(vm) { return createVMCard(vm); }).join('');
        container.innerHTML = '<div class="vm-grid">' + vmCards + '</div>';
    }

    lastUpdatedDiv.textContent = 'Last updated: ' + formatTimestamp(data.timestamp) + ' (' + data.vm_count + ' VMs found)';
}

function refreshData() {
    clearError();
    showLoading();

    cockpit.spawn(['/usr/bin/python3', '/usr/local/bin/nexus9000v_monitor.py', '--json'])
        .done(function(data) {
            hideLoading();
            try {
                const jsonData = JSON.parse(data);
                updateVMDisplay(jsonData);
            } catch (e) {
                showError('Failed to parse monitoring data: ' + e.message);
            }
        })
        .fail(function(error) {
            hideLoading();
            showError('Failed to retrieve VM data: ' + error.message);
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

