document.addEventListener('DOMContentLoaded', function () {
    const wrapper = document.getElementById('conversion-wrapper');
    if (!wrapper) {
        return;
    }

    const card = wrapper.querySelector('.conversion-card');
    const statusLabel = document.getElementById('conversion-status-label');
    const progressFill = document.getElementById('conversion-progress-fill');
    const overallText = document.getElementById('conversion-progress-overall');
    const fileText = document.getElementById('conversion-progress-file');
    const countsText = document.getElementById('conversion-counts');
    const etaText = document.getElementById('conversion-eta');
    const updatedText = document.getElementById('conversion-updated');
    const currentFileText = document.getElementById('conversion-current-file');
    const errorsContainer = document.getElementById('conversion-errors');
    const restartForm = document.getElementById('conversion-restart-form');

    const ACTIVE_STATUSES = ['running', 'scheduled', 'restarting'];

    function formatNumber(value, digits) {
        return value.toFixed(digits);
    }

    function pad(num) {
        return String(num).padStart(2, '0');
    }

    function formatEta(seconds) {
        if (typeof seconds !== 'number' || !isFinite(seconds)) {
            return '—';
        }
        const rounded = Math.max(0, Math.round(seconds));
        const hours = Math.floor(rounded / 3600);
        const minutes = Math.floor((rounded % 3600) / 60);
        const secs = rounded % 60;
        const parts = [];
        if (hours) parts.push(hours + 'ч');
        if (minutes) parts.push(minutes + 'м');
        parts.push(secs + 'с');
        return parts.join(' ');
    }

    function formatTimestamp(value) {
        if (!value) {
            return '—';
        }
        if (typeof value === 'string' && value.includes('T')) {
            const parsed = new Date(value);
            if (!Number.isNaN(parsed.getTime())) {
                return (
                    parsed.getFullYear() +
                    '-' + pad(parsed.getMonth() + 1) +
                    '-' + pad(parsed.getDate()) +
                    ' ' + pad(parsed.getHours()) +
                    ':' + pad(parsed.getMinutes()) +
                    ':' + pad(parsed.getSeconds())
                );
            }
        }
        return value;
    }

    function setActive(isActive) {
        wrapper.style.display = isActive ? '' : 'none';
        wrapper.dataset.active = isActive ? 'true' : 'false';
        if (restartForm) {
            restartForm.style.display = isActive ? '' : 'none';
        }
    }

    function updateStatus(data) {
        const status = (data.status || 'idle').toLowerCase();
        const total = data.total || 0;
        const processed = data.processed || 0;
        const current = data.current || null;
        const processedWithCurrent = processed + (current ? 1 : 0);
        const remainingValue = typeof data.remaining === 'number' ? data.remaining : Math.max(total - processed, 0);
        const remainingRounded = Math.max(0, Math.round(remainingValue));
        const overallPercent = typeof data.percent === 'number' ? Math.max(0, Math.min(data.percent, 100)) : 0;
        const filePercent = current && typeof current.percent === 'number' ? current.percent : null;
        const etaSeconds = current && typeof current.eta_seconds === 'number' ? current.eta_seconds : null;

        setActive(ACTIVE_STATUSES.includes(status));
        if (!card) return;
        card.dataset.status = status;

        if (statusLabel) {
            statusLabel.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            statusLabel.className = 'conversion-status conversion-status-' + status;
        }

        if (progressFill) {
            progressFill.style.width = overallPercent + '%';
        }
        if (overallText) {
            overallText.textContent = formatNumber(overallPercent, 1) + '%';
        }
        if (fileText) {
            fileText.textContent = filePercent !== null ? 'файл ' + formatNumber(filePercent, 1) + '%' : 'файл —';
        }

        if (countsText) {
            countsText.textContent = processedWithCurrent + '/' + total + ' • осталось ' + remainingRounded;
        }

        if (etaText) {
            if (current) {
                etaText.textContent = 'осталось ' + formatEta(etaSeconds);
            } else {
                etaText.textContent = 'осталось —';
            }
        }

        if (updatedText) {
            updatedText.textContent = formatTimestamp(data.last_update);
        }

        if (currentFileText) {
            currentFileText.textContent = current && current.file ? current.file : '—';
        }

        if (errorsContainer) {
            errorsContainer.innerHTML = '';
            if (Array.isArray(data.errors) && data.errors.length) {
                data.errors.forEach(function (error) {
                    const row = document.createElement('div');
                    row.className = 'conversion-error-row';

                    const header = document.createElement('div');
                    header.className = 'conversion-error-header';

                    const time = document.createElement('span');
                    time.className = 'conversion-error-time';
                    time.textContent = error.timestamp || '';
                    header.appendChild(time);

                    const file = document.createElement('span');
                    file.className = 'conversion-error-file';
                    file.textContent = error.file || '';
                    header.appendChild(file);

                    row.appendChild(header);

                    const message = document.createElement('div');
                    message.className = 'conversion-error-message';
                    message.textContent = error.message || '';
                    row.appendChild(message);

                    errorsContainer.appendChild(row);
                });
            }
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/admin/conversion/status', { cache: 'no-cache' });
            if (!response.ok) {
                throw new Error('Failed to fetch conversion status');
            }
            const payload = await response.json();
            updateStatus(payload);
        } catch (error) {
            console.warn(error);
        }
    }

    fetchStatus();
    setInterval(fetchStatus, 5000);
});
