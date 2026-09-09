/* =====================================================
   NotaryFlow - JavaScript Application Logic
   Handles API integration, form submission, and UI state
   ===================================================== */

const API_BASE_URL = '/api';

// ========================= UI State Management =========================

/**
 * Switch between view panels and update active navigation button
 * @param {string} viewId - The view identifier (dashboard, clients, new-session)
 * @param {HTMLElement} btn - The clicked button element
 */
function switchView(viewId, btn) {
    try {
        // Hide all view panels
        document.querySelectorAll('.view-panel').forEach(view => {
            view.classList.add('hidden');
        });

        // Show targeted view
        const targetView = document.getElementById(`view-${viewId}`);
        if (!targetView) {
            console.error(`View with id 'view-${viewId}' not found`);
            return;
        }
        targetView.classList.remove('hidden');

        // Update active navigation button
        document.querySelectorAll('.nav-btn').forEach(navBtn => {
            navBtn.classList.remove('active', 'bg-indigo-600', 'text-white');
            navBtn.classList.add('hover:bg-slate-800', 'text-slate-300');
            navBtn.removeAttribute('aria-current');
        });

        // Set current button as active
        if (btn) {
            btn.classList.add('active', 'bg-indigo-600', 'text-white');
            btn.classList.remove('hover:bg-slate-800', 'text-slate-300');
            btn.setAttribute('aria-current', 'page');
        }
    } catch (error) {
        console.error('Error switching view:', error);
    }
}

// ========================= Compliance & Validation =========================

/**
 * Validate ID expiry date and show compliance warnings
 */
function toggleIdRules() {
    const idType = document.getElementById('idType');
    const expiryInput = document.getElementById('idExpiry');
    const alertBox = document.getElementById('compliance-alert');

    if (!idType || !expiryInput || !alertBox) {
        console.warn('Required ID validation elements not found');
        return;
    }

    const idTypeValue = idType.value;
    alertBox.classList.add('hidden');

    // Check for Credible Witness
    if (idTypeValue === 'Credible Witness') {
        alertBox.textContent = "⚖️ Statutory Check: Credible witnesses must be personally known to the notary or present their own valid credentials under separate entries.";
        alertBox.classList.remove('hidden');
        return;
    }

    // Check for expired ID
    if (expiryInput.value) {
        const expiryDate = new Date(expiryInput.value + 'T23:59:59Z');
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        if (expiryDate <= today) {
            alertBox.textContent = "🚨 Non-Compliant: Stored Identification is expired. State regulations prohibit proceeding with expired identification documents.";
            alertBox.classList.remove('hidden');
        }
    }
}

// ========================= API Integration =========================

/**
 * Fetch commission information from API
 */
async function loadCommissionInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/commission`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();
        document.getElementById('commission-number').textContent = data.commission_number || 'N/A';
        document.getElementById('commission-expiry').textContent = data.expiry_date || 'N/A';
    } catch (error) {
        console.error('Error loading commission info:', error);
        document.getElementById('commission-info').innerHTML = 'Unable to load commission info';
    }
}

/**
 * Fetch dashboard metrics from API
 */
async function loadDashboardMetrics() {
    try {
        const response = await fetch(`${API_BASE_URL}/metrics?period=mtd`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();
        document.getElementById('metric-acts').textContent = data.total_acts || '0';
        document.getElementById('metric-fees').textContent = `$${(data.fees_collected || 0).toFixed(2)}`;
        document.getElementById('metric-pending').textContent = data.pending_signatures || '0';
    } catch (error) {
        console.error('Error loading metrics:', error);
        document.getElementById('metric-acts').innerHTML = '<span class="text-red-500">Error</span>';
    }
}

/**
 * Fetch and populate journal entries
 */
async function loadJournalEntries() {
    try {
        const response = await fetch(`${API_BASE_URL}/sessions`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const sessions = await response.json();
        const tableBody = document.getElementById('journal-table-body');

        if (!tableBody) {
            console.error('Journal table body not found');
            return;
        }

        if (!sessions || sessions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-gray-500">No journal entries found</td></tr>';
            return;
        }

        tableBody.innerHTML = sessions.map(session => {
            const dateStr = new Date(session.session_date).toLocaleString();
            const signerNames = session.clients
                ?.map(c => `${c.first_name} ${c.last_name}`)
                .join(', ') || 'N/A';
            const actType = session.acts?.[0]?.act_type?.value || 'Unknown';
            const fee = session.acts?.[0]?.statutory_fee || '0.00';
            const paymentStatus = session.payment_status?.value || 'Pending';
            const statusColor = paymentStatus === 'Paid' ? 'emerald' : 'amber';

            return `
                <tr class="hover:bg-gray-50/70">
                    <td class="p-4 font-medium text-slate-700">${dateStr}</td>
                    <td class="p-4 text-slate-600">${signerNames}</td>
                    <td class="p-4">
                        <span class="px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-md">
                            ${actType}
                        </span>
                    </td>
                    <td class="p-4 text-slate-600">$${parseFloat(fee).toFixed(2)}</td>
                    <td class="p-4">
                        <span class="px-2 py-1 bg-${statusColor}-50 text-${statusColor}-700 text-xs font-medium rounded-md">
                            ${paymentStatus}
                        </span>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading journal entries:', error);
        const tableBody = document.getElementById('journal-table-body');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-red-500">Error loading entries</td></tr>';
        }
    }
}

// ========================= Form Handlers =========================

/**
 * Handle client form submission
 */
async function handleClientFormSubmit(e) {
    e.preventDefault();

    const firstName = document.getElementById('firstName')?.value?.trim();
    const lastName = document.getElementById('lastName')?.value?.trim();
    const email = document.getElementById('email')?.value?.trim();
    const submitBtn = document.getElementById('submitClientBtn');
    const messageDiv = document.getElementById('clientFormMessage');

    // Validation
    if (!firstName || !lastName) {
        showMessage(messageDiv, 'First and last names are required', 'error');
        return;
    }

    // Disable button during submission
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding...';
    }

    try {
        const payload = {
            first_name: firstName,
            last_name: lastName,
            email: email || null
        };

        const response = await fetch(`${API_BASE_URL}/clients`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        showMessage(messageDiv, '✅ Client added successfully!', 'success');
        e.target.reset();

        // Reset button
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add to Database';
        }
    } catch (error) {
        console.error('Error adding client:', error);
        showMessage(messageDiv, '❌ Error adding client. Please try again.', 'error');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add to Database';
        }
    }
}

/**
 * Handle new session form submission
 */
async function handleSessionFormSubmit(e) {
    if (e && e.preventDefault) {
        e.preventDefault();
    }

    const actType = document.getElementById('actType')?.value;
    const idType = document.getElementById('idType')?.value;
    const idExpiry = document.getElementById('idExpiry')?.value;
    const docFile = document.getElementById('docFile')?.files?.[0];
    const submitBtn = document.getElementById('submitSessionBtn');
    const messageDiv = document.getElementById('sessionFormMessage');

    // Validation
    if (!actType || !idType || !idExpiry) {
        showMessage(messageDiv, 'All fields are required', 'error');
        return;
    }

    // Check compliance alert
    const complianceAlert = document.getElementById('compliance-alert');
    if (complianceAlert && !complianceAlert.classList.contains('hidden')) {
        showMessage(messageDiv, 'Please resolve compliance issues before proceeding', 'error');
        return;
    }

    // Disable button during submission
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging...';
    }

    try {
        const formData = new FormData();
        formData.append('act_type', actType);
        formData.append('id_type', idType);
        formData.append('id_expiry', idExpiry);
        if (docFile) {
            formData.append('document', docFile);
        }

        const response = await fetch(`${API_BASE_URL}/sessions`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        showMessage(messageDiv, '✅ Notarial act logged successfully!', 'success');
        
        // Reset form fields
        document.getElementById('actType').value = '';
        document.getElementById('idType').value = '';
        document.getElementById('idExpiry').value = '';
        document.getElementById('docFile').value = '';
        document.getElementById('compliance-alert').classList.add('hidden');

        // Reload journal entries
        await loadJournalEntries();

        // Reset button
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Log Notarial Act';
        }
    } catch (error) {
        console.error('Error logging session:', error);
        showMessage(messageDiv, '❌ Error logging act. Please try again.', 'error');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Log Notarial Act';
        }
    }
}

/**
 * Utility function to display form messages
 * @param {HTMLElement} messageDiv - The message container element
 * @param {string} message - The message text
 * @param {string} type - 'success' or 'error'
 */
function showMessage(messageDiv, message, type = 'success') {
    if (!messageDiv) return;

    messageDiv.textContent = message;
    messageDiv.className = `p-3 rounded-lg text-sm font-medium ${type}`;
    messageDiv.classList.remove('hidden');

    // Auto-hide success messages after 4 seconds
    if (type === 'success') {
        setTimeout(() => {
            messageDiv.classList.add('hidden');
        }, 4000);
    }
}

// ========================= Initialization =========================

/**
 * Initialize the application
 */
function initializeApp() {
    try {
        // Load initial data
        loadCommissionInfo();
        loadDashboardMetrics();
        loadJournalEntries();

        // Set up event listeners
        const clientForm = document.getElementById('clientForm');
        const idTypeSelect = document.getElementById('idType');
        const idExpiryInput = document.getElementById('idExpiry');
        const submitSessionBtn = document.getElementById('submitSessionBtn');

        if (clientForm) {
            clientForm.addEventListener('submit', handleClientFormSubmit);
        }

        if (idTypeSelect) {
            idTypeSelect.addEventListener('change', toggleIdRules);
        }

        if (idExpiryInput) {
            idExpiryInput.addEventListener('change', toggleIdRules);
        }

        if (submitSessionBtn) {
            submitSessionBtn.addEventListener('click', handleSessionFormSubmit);
        }

        console.log('NotaryFlow application initialized successfully');
    } catch (error) {
        console.error('Error initializing application:', error);
    }
}

// ========================= Application Startup =========================

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// Refresh data periodically (every 30 seconds)
setInterval(() => {
    const activeView = document.querySelector('.view-panel:not(.hidden)');
    if (activeView && activeView.id === 'view-dashboard') {
        loadDashboardMetrics();
        loadJournalEntries();
    }
}, 30000);