// Get configuration from window object
const { HOST, API_PREFIX, API_KEY } = window.WEBHOOK_CONFIG;

// Prevent default form submission for all forms
document.addEventListener('DOMContentLoaded', function() {
    // Prevent all forms from submitting normally
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        });
    });
    
    // Initialize form handlers
    initializeFormHandlers();
});

// Copy API Key to clipboard
function copyApiKey(e) {
    if (e) e.preventDefault();
    navigator.clipboard.writeText(API_KEY).then(() => {
        const btn = e.target;
        const originalText = btn.textContent;
        btn.textContent = '✅ Скопировано!';
        btn.style.background = '#4caf50';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '#ff9800';
        }, 2000);
    }).catch(err => {
        alert('Ошибка копирования: ' + err);
    });
}

// Toggle API Key visibility
function toggleApiKeyVisibility(e) {
    if (e) e.preventDefault();
    const hiddenEl = document.getElementById('api-key-hidden');
    const visibleEl = document.getElementById('api-key-visible');
    const btn = e ? e.target : null;
    
    if (hiddenEl.style.display === 'none') {
        hiddenEl.style.display = 'inline';
        visibleEl.style.display = 'none';
        if (btn) btn.textContent = '👁️ Показать';
    } else {
        hiddenEl.style.display = 'none';
        visibleEl.style.display = 'inline';
        if (btn) btn.textContent = '🙈 Скрыть';
    }
}

// Tab switching
function switchTab(tabName, e) {
    if (e) e.preventDefault();
    
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    document.getElementById(tabName + '-tab').classList.add('active');
    
    // Add active class to clicked tab
    if (e && e.target) e.target.classList.add('active');
}

// Example data functions
function fillGsKeysExample(e) {
    if (e) e.preventDefault();
    const textarea = document.querySelector('#form-user-update textarea[name="gs_keys"]');
    textarea.value = JSON.stringify([
        {"key_number": "GS-12345-ABCDE", "action": "add"},
        {"key_number": "GS-67890-FGHIJ", "action": "add"}
    ], null, 2);
}

function fillOrganizationsExample(e) {
    if (e) e.preventDefault();
    const textarea = document.querySelector('#form-user-update textarea[name="organizations"]');
    textarea.value = JSON.stringify([
        {"inn": "7707083893", "action": "add"},
        {"inn": "5004002123", "action": "add"}
    ], null, 2);
}

// Show request preview
function showRequestPreview(formId, endpoint, headers, payload) {
    const previewEl = document.getElementById(`request-preview-${formId}`);
    const dataEl = document.getElementById(`request-data-${formId}`);
    
    if (!previewEl || !dataEl) return;
    
    const requestInfo = {
        method: 'POST',
        url: `${HOST}${API_PREFIX}${endpoint}`,
        headers: headers,
        body: payload
    };
    
    dataEl.textContent = JSON.stringify(requestInfo, null, 2);
    previewEl.style.display = 'block';
}

// Helper function to send webhook request with preview
async function sendWebhookRequestWithPreview(formId, endpoint, payload) {
    const headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    };
    
    // Show request preview
    showRequestPreview(formId, endpoint, headers, payload);
    
    const responseEl = document.getElementById(`response-${formId}`);
    if (!responseEl) return;
    
    responseEl.style.display = 'none';
    
    try {
        const response = await fetch(`${HOST}${API_PREFIX}${endpoint}`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        responseEl.textContent = JSON.stringify(result, null, 2);
        responseEl.className = 'response ' + (response.ok ? 'success' : 'error');
        responseEl.style.display = 'block';
        
        return result;
    } catch (error) {
        responseEl.textContent = `Ошибка: ${error.message}`;
        responseEl.className = 'response error';
        responseEl.style.display = 'block';
        throw error;
    }
}

// Initialize all form handlers
function initializeFormHandlers() {
    // 1. Registration Status
    const formRegistration = document.getElementById('form-registration');
    if (formRegistration) {
        formRegistration.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            
            if (!messengerUserId) {
                alert(`Ошибка: У выбранного пользователя нет MAX ID. Выберите другого пользователя.`);
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                phone: data.phone,
                status: data.status
            };
            
            if (data.status === 'approved') {
                if (data.manager_name) payload.manager_name = data.manager_name;
                if (data.manager_id) {
                    const messengerManagerId = e.target.dataset.selectedManagerMaxUserId;
                    if (!messengerManagerId) {
                        alert(`Ошибка: У выбранного менеджера нет MAX ID. Выберите другого менеджера.`);
                        return;
                    }
                    payload.manager_id = parseInt(messengerManagerId);
                }
                if (data.subscription_status) payload.subscription_status = data.subscription_status;
                if (data.support_expires_at) payload.support_expires_at = new Date(data.support_expires_at).toISOString();
            } else {
                if (data.reason) payload.reason = data.reason;
            }
            
            await sendWebhookRequestWithPreview('registration', '/webhooks/registration_status', payload);
        });
    }
    
    // 2. User Update
    const formUserUpdate = document.getElementById('form-user-update');
    if (formUserUpdate) {
        formUserUpdate.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            
            if (!messengerUserId) {
                alert(`Ошибка: У выбранного пользователя нет MAX ID. Выберите другого пользователя.`);
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                phone: data.phone
            };
            
            if (data.email) payload.email = data.email;
            if (data.full_name) payload.full_name = data.full_name;
            if (data.subscription_end_date) payload.subscription_end_date = new Date(data.subscription_end_date).toISOString();
            if (data.subscription_status) payload.subscription_status = data.subscription_status;
            if (data.gs_keys) payload.gs_keys = JSON.parse(data.gs_keys);
            if (data.organizations) payload.organizations = JSON.parse(data.organizations);
            
            await sendWebhookRequestWithPreview('user-update', '/webhooks/user_update', payload);
        });
    }
    
    // Add more form handlers here as needed
    // TODO: Add handlers for forms 3-10
}

// Export functions for inline onclick handlers
window.copyApiKey = copyApiKey;
window.toggleApiKeyVisibility = toggleApiKeyVisibility;
window.switchTab = switchTab;
window.fillGsKeysExample = fillGsKeysExample;
window.fillOrganizationsExample = fillOrganizationsExample;

    // 3. Payment Confirmed (NPS)
    const formPayment = document.getElementById('form-payment');
    if (formPayment) {
        formPayment.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            
            if (!messengerUserId) {
                alert(`Ошибка: У выбранного пользователя нет MAX ID. Выберите другого пользователя.`);
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                payment_date: new Date(data.payment_date).toISOString()
            };
            
            await sendWebhookRequestWithPreview('payment', '/webhooks/payment_confirmed', payload);
        });
    }
    
    // 4. Renewal Reminder Test
    const formRenewalReminder = document.getElementById('form-renewal-reminder');
    if (formRenewalReminder) {
        formRenewalReminder.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            
            if (!messengerUserId) {
                alert('Ошибка: У выбранного пользователя нет MAX ID.');
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                reminder_type: data.reminder_type
            };
            
            await sendWebhookRequestWithPreview('renewal-reminder', '/webhooks/test_renewal_reminder', payload);
        });
    }
    
    // 5. Key Conflict Resolution
    const formKeyConflict = document.getElementById('form-key-conflict');
    if (formKeyConflict) {
        formKeyConflict.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            
            // Get MAX IDs from the select elements (not form dataset)
            const newUserSelect = e.target.querySelector('[name="new_user_id"]');
            const oldUserSelect = e.target.querySelector('[name="old_user_id"]');
            const staffSelect = e.target.querySelector('[name="resolved_by_staff_id"]');
            
            const newUserMaxId = newUserSelect?.dataset.selectedMaxUserId;
            const oldUserMaxId = oldUserSelect?.dataset.selectedMaxUserId;
            const staffMaxId = staffSelect?.dataset.selectedMaxUserId;
            
            if (!newUserMaxId) {
                alert('Ошибка: У выбранного нового пользователя нет MAX ID. Выберите другого пользователя.');
                return;
            }
            
            if (!oldUserMaxId) {
                alert('Ошибка: У выбранного старого пользователя нет MAX ID. Выберите другого пользователя.');
                return;
            }
            
            if (!staffMaxId) {
                alert('Ошибка: У выбранного сотрудника нет MAX ID. Выберите другого сотрудника.');
                return;
            }
            
            const payload = {
                messenger: messenger,
                new_user_id: parseInt(newUserMaxId),
                old_user_id: parseInt(oldUserMaxId),
                gs_key: data.gs_key,
                resolution: data.resolution,
                reason: data.reason || undefined,
                resolved_by_staff_id: parseInt(staffMaxId)
            };
            
            await sendWebhookRequestWithPreview('key-conflict', '/webhooks/key_conflict_resolution', payload);
        });
    }
    
    // 6. Manager Assignment
    const formManagerAssignment = document.getElementById('form-manager-assignment');
    if (formManagerAssignment) {
        formManagerAssignment.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            const messengerManagerId = e.target.dataset.selectedManagerMaxUserId;
            
            if (!messengerUserId) {
                alert('Ошибка: У выбранного пользователя нет MAX ID.');
                return;
            }
            
            if (!messengerManagerId) {
                alert('Ошибка: У выбранного менеджера нет MAX ID.');
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                phone: data.phone,
                manager_id: parseInt(messengerManagerId),
                send_notification: formData.get('send_notification') === 'on'
            };
            
            if (data.manager_name) payload.manager_name = data.manager_name;
            
            await sendWebhookRequestWithPreview('manager-assignment', '/webhooks/manager_assignment', payload);
        });
    }
    
    // 7. Staff Update
    const formStaffUpdate = document.getElementById('form-staff-update');
    if (formStaffUpdate) {
        formStaffUpdate.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerStaffId = e.target.dataset.selectedManagerMaxUserId;
            
            if (!messengerStaffId) {
                alert('Ошибка: У выбранного сотрудника нет MAX ID. Выберите другого сотрудника.');
                return;
            }
            
            const updates = {};
            if (data.full_name) updates.full_name = data.full_name;
            if (data.position) updates.position = data.position;
            updates.is_active = formData.get('is_active') === 'on';
            if (data.backup_managers) {
                updates.backup_managers = data.backup_managers.split(',').map(id => parseInt(id.trim()));
            }
            
            const payload = {
                messenger: messenger,
                staff_id: parseInt(messengerStaffId),
                updates: updates
            };
            
            await sendWebhookRequestWithPreview('staff-update', '/webhooks/staff_update', payload);
        });
    }
    
    // 8. Ticket Status Update
    const formTicketStatus = document.getElementById('form-ticket-status');
    if (formTicketStatus) {
        formTicketStatus.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const payload = {
                ticket_id: data.ticket_id,
                status: data.status,
                comment: data.comment || undefined
            };
            
            // Add closed_by_staff_id if provided (must be messenger-specific ID)
            if (data.closed_by_staff_id) {
                const staffSelect = e.target.querySelector('[name="closed_by_staff_id"]');
                const staffMaxId = staffSelect?.dataset.selectedMaxUserId;
                
                if (!staffMaxId) {
                    alert('Ошибка: У выбранного сотрудника нет MAX ID. Выберите другого сотрудника.');
                    return;
                }
                
                payload.closed_by_staff_id = parseInt(staffMaxId);
            }
            
            await sendWebhookRequestWithPreview('ticket-status', '/webhooks/ticket_status_update', payload);
        });
    }
    
    // 9. Subscription Status Change
    const formSubscription = document.getElementById('form-subscription');
    if (formSubscription) {
        formSubscription.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            const messengerUserId = e.target.dataset.selectedMaxUserId;
            
            if (!messengerUserId) {
                alert('Ошибка: У выбранного пользователя нет MAX ID.');
                return;
            }
            
            const payload = {
                messenger: messenger,
                user_id: parseInt(messengerUserId),
                subscription_status: data.subscription_status,
                subscription_end_date: data.subscription_end_date ? new Date(data.subscription_end_date).toISOString() : undefined,
                support_type: data.support_type || undefined
            };
            
            await sendWebhookRequestWithPreview('subscription', '/webhooks/subscription_status_change', payload);
        });
    }
    
    // 10. Broadcast Campaign
    const formBroadcast = document.getElementById('form-broadcast');
    if (formBroadcast) {
        formBroadcast.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const sendNow = document.getElementById('send_now')?.checked || false;
            
            const payload = {
                campaign_id: data.campaign_id,
                message_text: data.message_text,
                target_audience: data.target_audience,
                messenger: 'max',
                manager_messenger_id: parseInt(data.manager_messenger_id),
                send_now: sendNow,
                schedule_time: sendNow ? new Date().toISOString() : new Date(data.schedule_time).toISOString()
            };
            
            await sendWebhookRequestWithPreview('broadcast', '/webhooks/broadcast_campaign', payload);
        });
    }
    
    // 11. Ticket Reassignment
    const formTicketReassignment = document.getElementById('form-ticket-reassignment');
    if (formTicketReassignment) {
        formTicketReassignment.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const messenger = 'max';
            
            // Get MAX IDs from dataset (stored by setupStaffAutoFill)
            const fromStaffSelect = e.target.querySelector('[name="from_staff_id"]');
            const toStaffSelect = e.target.querySelector('[name="to_staff_id"]');
            
            const fromStaffOption = fromStaffSelect.options[fromStaffSelect.selectedIndex];
            const toStaffOption = toStaffSelect.options[toStaffSelect.selectedIndex];
            
            const fromStaffMaxId = fromStaffOption.dataset.maxUserId;
            const toStaffMaxId = toStaffOption.dataset.maxUserId;
            
            if (!fromStaffMaxId) {
                alert('Ошибка: У выбранного сотрудника (From Staff) нет MAX ID. Выберите другого сотрудника.');
                return;
            }
            
            if (!toStaffMaxId) {
                alert('Ошибка: У выбранного сотрудника (To Staff) нет MAX ID. Выберите другого сотрудника.');
                return;
            }
            
            // Handle ticket_ids - either "all" or comma-separated list
            let ticketIds;
            const reassignAll = formData.get('reassign_all') === 'on';
            
            if (reassignAll) {
                ticketIds = ['all'];
            } else {
                const ticketIdsInput = data.ticket_ids.trim();
                ticketIds = ticketIdsInput.split(',').map(id => id.trim());
            }
            
            const payload = {
                from_staff_id: parseInt(fromStaffMaxId),
                to_staff_id: parseInt(toStaffMaxId),
                ticket_ids: ticketIds,
                messenger: messenger,
                reason: data.reason
            };
            
            await sendWebhookRequestWithPreview('ticket-reassignment', '/webhooks/ticket_reassignment', payload);
        });
    }
    
    // 12. Ticket History API
    const formTicketHistory = document.getElementById('form-ticket-history');
    if (formTicketHistory) {
        formTicketHistory.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const ticketId = data.ticket_id;
            const responseEl = document.getElementById('response-ticket-history');
            
            responseEl.style.display = 'none';
            responseEl.textContent = 'Получение истории тикета...';
            responseEl.className = 'response';
            responseEl.style.display = 'block';
            
            try {
                const response = await fetch(`${HOST}${API_PREFIX}/tickets/${ticketId}/history`, {
                    method: 'GET',
                    headers: {
                        'X-API-Key': API_KEY
                    }
                });
                
                const result = await response.json();
                responseEl.textContent = JSON.stringify(result, null, 2);
                responseEl.className = 'response ' + (response.ok ? 'success' : 'error');
                responseEl.style.display = 'block';
            } catch (error) {
                responseEl.textContent = `Ошибка: ${error.message}`;
                responseEl.className = 'response error';
                responseEl.style.display = 'block';
            }
        });
    }
    
    // 13. Escalation Test API
    const formEscalationTest = document.getElementById('form-escalation-test');
    if (formEscalationTest) {
        formEscalationTest.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const payload = {
                ticket_id: parseInt(data.ticket_id),
                force_escalation: formData.get('force_escalation') === 'on'
            };
            
            await sendWebhookRequestWithPreview('escalation-test', '/escalation/test', payload);
        });
    }
    
    // 14. Backup Manager Test API
    const formBackupManagerTest = document.getElementById('form-backup-manager-test');
    if (formBackupManagerTest) {
        formBackupManagerTest.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const payload = {
                ticket_id: parseInt(data.ticket_id)
            };
            
            if (data.target_backup_slot) {
                payload.target_backup_slot = parseInt(data.target_backup_slot);
            }
            
            await sendWebhookRequestWithPreview('backup-manager-test', '/escalation/test-backup-reassignment', payload);
        });
    }



// Test NPS Survey - send immediately
async function testNpsSurvey(e) {
    if (e) e.preventDefault();
    const form = document.getElementById('form-payment');
    const formData = new FormData(form);
    const data = Object.fromEntries(formData);
    
    if (!data.user_id) {
        alert('Пожалуйста, выберите пользователя');
        return;
    }
    
    const messenger = 'max';
    const messengerUserId = form.dataset.selectedMaxUserId;
    
    if (!messengerUserId) {
        alert(`Ошибка: У выбранного пользователя нет MAX ID. Выберите другого пользователя.`);
        return;
    }
    
    const payload = {
        messenger: messenger,
        user_id: parseInt(messengerUserId),
        survey_type: "loyalty",
        trigger_event_id: 0,
        event_date: new Date().toISOString()
    };
    
    const responseEl = document.getElementById('response-payment');
    responseEl.style.display = 'none';
    responseEl.textContent = 'Отправка тестового опроса...';
    responseEl.className = 'response';
    responseEl.style.display = 'block';
    
    try {
        const response = await fetch(`${HOST}${API_PREFIX}/webhooks/test_nps_survey`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': API_KEY
            },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        responseEl.textContent = JSON.stringify(result, null, 2);
        responseEl.className = 'response ' + (response.ok ? 'success' : 'error');
        responseEl.style.display = 'block';
    } catch (error) {
        responseEl.textContent = `Ошибка: ${error.message}`;
        responseEl.className = 'response error';
        responseEl.style.display = 'block';
    }
}

// Get current work mode
async function getCurrentWorkMode(e) {
    if (e) e.preventDefault();
    const responseEl = document.getElementById('response-calendar-rule');
    const selectEl = document.getElementById('work_mode_display');
    
    responseEl.style.display = 'none';
    responseEl.textContent = 'Проверка текущего режима работы...';
    responseEl.className = 'response';
    responseEl.style.display = 'block';
    
    try {
        const response = await fetch(`${HOST}${API_PREFIX}/calendar/current-mode`, {
            method: 'GET',
            headers: {
                'X-API-Key': API_KEY
            }
        });
        
        const result = await response.json();
        
        // Update select display
        if (response.ok && result.work_mode) {
            selectEl.innerHTML = '';
            const option = document.createElement('option');
            option.value = result.work_mode;
            option.selected = true;
            
            const modeLabels = {
                'REGULAR': 'REGULAR (обычные часы, заявки менеджерам)',
                'EXTENDED': 'EXTENDED (расширенные часы, дежурным)',
                'NON_WORKING': 'NON_WORKING (нерабочее время, в очередь)'
            };
            
            option.textContent = modeLabels[result.work_mode] || result.work_mode;
            selectEl.appendChild(option);
        }
        
        responseEl.textContent = JSON.stringify(result, null, 2);
        responseEl.className = 'response ' + (response.ok ? 'success' : 'error');
        responseEl.style.display = 'block';
    } catch (error) {
        responseEl.textContent = `Ошибка: ${error.message}`;
        responseEl.className = 'response error';
        responseEl.style.display = 'block';
    }
}

// Toggle schedule time field visibility
function toggleScheduleTime(e) {
    if (e) e.preventDefault();
    const sendNowCheckbox = document.getElementById('send_now');
    const scheduleTimeGroup = document.getElementById('schedule-time-group');
    const scheduleTimeInput = document.getElementById('schedule_time');
    
    if (sendNowCheckbox && scheduleTimeGroup && scheduleTimeInput) {
        if (sendNowCheckbox.checked) {
            scheduleTimeGroup.style.display = 'none';
            scheduleTimeInput.removeAttribute('required');
        } else {
            scheduleTimeGroup.style.display = 'block';
            scheduleTimeInput.setAttribute('required', 'required');
        }
    }
}
window.testNpsSurvey = testNpsSurvey;
window.getCurrentWorkMode = getCurrentWorkMode;
window.toggleScheduleTime = toggleScheduleTime;

// Toggle ticket IDs field visibility based on "reassign all" checkbox
function toggleTicketIdsField(e) {
    if (e) e.preventDefault();
    const reassignAllCheckbox = document.getElementById('reassign_all');
    const ticketIdsGroup = document.getElementById('ticket-ids-group');
    const ticketIdsInput = document.getElementById('ticket_ids_input');
    
    if (reassignAllCheckbox && ticketIdsGroup && ticketIdsInput) {
        if (reassignAllCheckbox.checked) {
            ticketIdsGroup.style.display = 'none';
            ticketIdsInput.removeAttribute('required');
            ticketIdsInput.value = '';
        } else {
            ticketIdsGroup.style.display = 'block';
            ticketIdsInput.setAttribute('required', 'required');
        }
    }
}
window.toggleTicketIdsField = toggleTicketIdsField;
