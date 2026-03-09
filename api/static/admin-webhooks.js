/**
 * Admin Webhooks Panel - Dynamic Data Loading
 * 
 * Handles dynamic loading of users and staff members for webhook forms.
 */

// Get API configuration from parent page
const getApiConfig = () => {
    // Try to get from parent window (admin panel)
    if (typeof HOST !== 'undefined' && typeof API_KEY !== 'undefined') {
        return { host: HOST, apiKey: API_KEY, prefix: API_PREFIX || '/bot/api' };
    }
    // Fallback to defaults
    return {
        host: window.location.origin,
        apiKey: 'mJNc4TQdzd5eVNh3ygtMvdcmggxCX58uK2kVNPr3CYI',
        prefix: '/bot/api'
    };
};

// Cache for loaded data
const dataCache = {
    users: {},
    staff: {}
};

/**
 * Clear cache for users or staff
 */
function clearCache(type = 'all') {
    if (type === 'users' || type === 'all') {
        dataCache.users = {};
    }
    if (type === 'staff' || type === 'all') {
        dataCache.staff = {};
    }
}

/**
 * Load users list from API
 */
async function loadUsers(messenger = 'all', search = '', forceRefresh = false) {
    const cacheKey = `${messenger}_${search}`;
    
    // Return cached data if available and not forcing refresh
    if (!forceRefresh && dataCache.users[cacheKey]) {
        return dataCache.users[cacheKey];
    }
    
    try {
        const config = getApiConfig();
        // Include status=all to show all users except rejected
        const params = new URLSearchParams({ messenger, search, status: 'all', limit: 500 });
        const response = await fetch(`${config.prefix}/admin/users?${params}`, {
            headers: {
                'X-API-Key': config.apiKey
            }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            dataCache.users[cacheKey] = data.users;
            return data.users;
        }
        
        console.error('Failed to load users:', data.message);
        return [];
    } catch (error) {
        console.error('Error loading users:', error);
        return [];
    }
}

/**
 * Load staff list from API
 */
async function loadStaff(messenger = 'all', search = '', forceRefresh = false) {
    const cacheKey = `${messenger}_${search}`;
    
    // Return cached data if available and not forcing refresh
    if (!forceRefresh && dataCache.staff[cacheKey]) {
        return dataCache.staff[cacheKey];
    }
    
    try {
        const config = getApiConfig();
        const params = new URLSearchParams({ messenger, search, limit: 500 });
        const response = await fetch(`${config.prefix}/admin/staff?${params}`, {
            headers: {
                'X-API-Key': config.apiKey
            }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            dataCache.staff[cacheKey] = data.staff;
            return data.staff;
        }
        
        console.error('Failed to load staff:', data.message);
        return [];
    } catch (error) {
        console.error('Error loading staff:', error);
        return [];
    }
}

/**
 * Get user details by ID
 */
async function getUserDetails(userId) {
    try {
        const config = getApiConfig();
        const response = await fetch(`${config.prefix}/admin/user/${userId}`, {
            headers: {
                'X-API-Key': config.apiKey
            }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            return data.user;
        }
        
        console.error('Failed to load user details:', data.message);
        return null;
    } catch (error) {
        console.error('Error loading user details:', error);
        return null;
    }
}

/**
 * Get staff details by ID
 */
async function getStaffDetails(staffId) {
    try {
        const config = getApiConfig();
        const response = await fetch(`${config.prefix}/admin/staff/${staffId}`, {
            headers: {
                'X-API-Key': config.apiKey
            }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            return data.staff;
        }
        
        console.error('Failed to load staff details:', data.message);
        return null;
    } catch (error) {
        console.error('Error loading staff details:', error);
        return null;
    }
}

/**
 * Populate select element with users
 */
async function populateUserSelect(selectElement, messenger = 'all', forceRefresh = false) {
    const users = await loadUsers(messenger, '', forceRefresh);
    
    // Clear existing options except placeholder
    selectElement.innerHTML = '<option value="">-- Выберите пользователя --</option>';
    
    // Add user options
    users.forEach(user => {
        const option = document.createElement('option');
        option.value = user.id;
        option.textContent = user.display;
        option.dataset.userId = user.id;
        option.dataset.tgUserId = user.tg_user_id || '';
        option.dataset.maxUserId = user.max_user_id || '';
        option.dataset.phone = user.phone || '';
        option.dataset.fullName = user.full_name || '';
        option.dataset.createdAt = user.created_at || '';
        option.dataset.registrationStatus = user.registration_status || '';
        selectElement.appendChild(option);
    });
}

/**
 * Populate select element with staff
 */
async function populateStaffSelect(selectElement, messenger = 'all', forceRefresh = false) {
    const staff = await loadStaff(messenger, '', forceRefresh);
    
    // Clear existing options except placeholder
    selectElement.innerHTML = '<option value="">-- Выберите сотрудника --</option>';
    
    // Add staff options
    staff.forEach(member => {
        const option = document.createElement('option');
        option.value = member.id;
        option.textContent = member.display;
        option.dataset.staffId = member.id;
        option.dataset.tgUserId = member.tg_user_id || '';
        option.dataset.maxUserId = member.max_user_id || '';
        option.dataset.fullName = member.full_name || '';
        option.dataset.position = member.position || '';
        option.dataset.role = member.role || '';
        option.dataset.isActive = member.is_active || false;
        selectElement.appendChild(option);
    });
}

/**
 * Auto-fill form fields when user is selected
 */
function setupUserAutoFill(selectElement, form) {
    selectElement.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        
        if (!selectedOption.value) return;
        
        // Fill phone field
        const phoneField = form.querySelector('[name="phone"]');
        if (phoneField && phoneField.tagName === 'INPUT') {
            phoneField.value = selectedOption.dataset.phone || '';
        }
        
        // Fill full_name field
        const fullNameField = form.querySelector('[name="full_name"]');
        if (fullNameField && fullNameField.tagName === 'INPUT') {
            fullNameField.value = selectedOption.dataset.fullName || '';
        }
        
        // Fill max_user_id field
        const maxUserIdField = form.querySelector('[name="max_user_id"]');
        if (maxUserIdField && maxUserIdField.tagName === 'INPUT') {
            maxUserIdField.value = selectedOption.dataset.maxUserId || '';
        }
        
        // Fill tg_user_id field
        const tgUserIdField = form.querySelector('[name="tg_user_id"]');
        if (tgUserIdField && tgUserIdField.tagName === 'INPUT') {
            tgUserIdField.value = selectedOption.dataset.tgUserId || '';
        }
        
        // Store messenger-specific IDs in data attributes on the SELECT element itself
        // This allows multiple user selects in the same form (e.g., key conflict form)
        this.dataset.selectedMaxUserId = selectedOption.dataset.maxUserId || '';
        this.dataset.selectedTgUserId = selectedOption.dataset.tgUserId || '';
        
        // Also store on form for backward compatibility with single-user forms
        form.dataset.selectedMaxUserId = selectedOption.dataset.maxUserId || '';
        form.dataset.selectedTgUserId = selectedOption.dataset.tgUserId || '';
    });
}

/**
 * Auto-fill form fields when staff is selected
 */
function setupStaffAutoFill(selectElement, form) {
    selectElement.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        
        if (!selectedOption.value) return;
        
        // Fill manager_name field
        const managerNameField = form.querySelector('[name="manager_name"]');
        if (managerNameField && managerNameField.tagName === 'INPUT') {
            managerNameField.value = selectedOption.dataset.fullName || '';
        }
        
        // Fill full_name field
        const fullNameField = form.querySelector('[name="full_name"]');
        if (fullNameField && fullNameField.tagName === 'INPUT') {
            fullNameField.value = selectedOption.dataset.fullName || '';
        }
        
        // Fill position field
        const positionField = form.querySelector('[name="position"]');
        if (positionField && positionField.tagName === 'INPUT') {
            positionField.value = selectedOption.dataset.position || '';
        }
        
        // Fill max_user_id field
        const maxUserIdField = form.querySelector('[name="max_user_id"]');
        if (maxUserIdField && maxUserIdField.tagName === 'INPUT') {
            maxUserIdField.value = selectedOption.dataset.maxUserId || '';
        }
        
        // Fill tg_user_id field
        const tgUserIdField = form.querySelector('[name="tg_user_id"]');
        if (tgUserIdField && tgUserIdField.tagName === 'INPUT') {
            tgUserIdField.value = selectedOption.dataset.tgUserId || '';
        }
        
        // Store messenger-specific IDs in data attributes on the SELECT element itself
        // This allows multiple staff selects in the same form
        this.dataset.selectedMaxUserId = selectedOption.dataset.maxUserId || '';
        this.dataset.selectedTgUserId = selectedOption.dataset.tgUserId || '';
        
        // Also store on form for backward compatibility with single-staff forms
        form.dataset.selectedManagerMaxUserId = selectedOption.dataset.maxUserId || '';
        form.dataset.selectedManagerTgUserId = selectedOption.dataset.tgUserId || '';
    });
}

/**
 * Setup messenger change handler to reload selects
 */
function setupMessengerChangeHandler(messengerSelect, form) {
    messengerSelect.addEventListener('change', async function() {
        // Always load all users regardless of messenger selection
        const messenger = 'all';
        
        // Reload user selects
        const userSelects = form.querySelectorAll('select[data-type="user"]');
        for (const select of userSelects) {
            await populateUserSelect(select, messenger, true);
        }
        
        // Reload staff selects
        const staffSelects = form.querySelectorAll('select[data-type="staff"]');
        for (const select of staffSelects) {
            await populateStaffSelect(select, messenger, true);
        }
    });
}

/**
 * Initialize all dynamic selects in a form
 */
async function initializeFormSelects(form) {
    const messengerSelect = form.querySelector('[name="messenger"]');
    // Always load all users regardless of messenger selection
    const messenger = 'all';
    
    // Initialize user selects
    const userSelects = form.querySelectorAll('select[data-type="user"]');
    for (const select of userSelects) {
        await populateUserSelect(select, messenger);
        setupUserAutoFill(select, form);
    }
    
    // Initialize staff selects
    const staffSelects = form.querySelectorAll('select[data-type="staff"]');
    for (const select of staffSelects) {
        await populateStaffSelect(select, messenger);
        setupStaffAutoFill(select, form);
    }
    
    // Setup messenger change handler - but still load all users
    if (messengerSelect) {
        setupMessengerChangeHandler(messengerSelect, form);
    }
}

/**
 * Initialize all forms on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    // Find all forms with dynamic selects
    const forms = document.querySelectorAll('form[data-dynamic-selects="true"]');
    
    forms.forEach(form => {
        initializeFormSelects(form);
    });
});

/**
 * Add search functionality to selects
 */
function addSearchToSelect(selectElement) {
    const wrapper = document.createElement('div');
    wrapper.className = 'select-with-search';
    
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Поиск...';
    searchInput.className = 'select-search';
    
    selectElement.parentNode.insertBefore(wrapper, selectElement);
    wrapper.appendChild(searchInput);
    wrapper.appendChild(selectElement);
    
    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        const options = selectElement.options;
        
        for (let i = 1; i < options.length; i++) {
            const option = options[i];
            const text = option.textContent.toLowerCase();
            
            if (text.includes(searchTerm)) {
                option.style.display = '';
            } else {
                option.style.display = 'none';
            }
        }
    });
}


/**
 * Add refresh button to select wrapper
 */
function addRefreshButton(selectElement, form) {
    const wrapper = selectElement.closest('.select-with-search') || selectElement.parentElement;
    
    // Check if refresh button already exists
    if (wrapper.querySelector('.refresh-btn')) {
        return;
    }
    
    const refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'refresh-btn';
    refreshBtn.innerHTML = '🔄';
    refreshBtn.title = 'Обновить список';
    refreshBtn.style.cssText = `
        position: absolute;
        right: 5px;
        top: 50%;
        transform: translateY(-50%);
        background: #1976d2;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 5px 10px;
        cursor: pointer;
        font-size: 14px;
        z-index: 10;
    `;
    
    refreshBtn.addEventListener('click', async function() {
        this.disabled = true;
        this.innerHTML = '⏳';
        
        try {
            // Clear cache
            clearCache();
            
            // Always load all users regardless of messenger selection
            const messenger = 'all';
            
            // Reload user selects
            const userSelects = form.querySelectorAll('select[data-type="user"]');
            for (const select of userSelects) {
                await populateUserSelect(select, messenger, true);
            }
            
            // Reload staff selects
            const staffSelects = form.querySelectorAll('select[data-type="staff"]');
            for (const select of staffSelects) {
                await populateStaffSelect(select, messenger, true);
            }
            
            this.innerHTML = '✓';
            setTimeout(() => {
                this.innerHTML = '🔄';
                this.disabled = false;
            }, 1000);
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.innerHTML = '✗';
            setTimeout(() => {
                this.innerHTML = '🔄';
                this.disabled = false;
            }, 2000);
        }
    });
    
    // Make wrapper position relative
    wrapper.style.position = 'relative';
    wrapper.appendChild(refreshBtn);
}

/**
 * Initialize refresh buttons for all selects
 */
function initializeRefreshButtons() {
    const forms = document.querySelectorAll('form[data-dynamic-selects="true"]');
    
    forms.forEach(form => {
        const selects = form.querySelectorAll('select[data-type="user"], select[data-type="staff"]');
        selects.forEach(select => {
            addRefreshButton(select, form);
        });
    });
}

// Initialize refresh buttons after DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for forms to be initialized
    setTimeout(initializeRefreshButtons, 500);
});
