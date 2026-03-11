# Admin Panel Structure

## Overview

The admin panel for webhook testing has been refactored into separate files for better maintainability and scalability.

## File Structure

```
api/
├── admin_panel.py          # FastAPI route handler
├── templates/
│   └── admin_webhooks.html # HTML template
└── static/
    ├── admin-webhooks.css  # Styles
    ├── webhook-forms.js    # Form handling logic
    └── admin-webhooks.js   # Dynamic selects (existing)
```

## Components

### 1. `admin_panel.py`
- FastAPI router with single endpoint `/admin/webhooks`
- Passes configuration to template (HOST, API_PREFIX, API_KEY)
- Clean Python code without embedded HTML

### 2. `templates/admin_webhooks.html`
- Jinja2 template with webhook testing forms
- Uses template variables for configuration
- Loads external CSS and JS files
- Modular structure for easy form additions

### 3. `static/admin-webhooks.css`
- All styling for the admin panel
- Responsive design
- Consistent color scheme and spacing

### 4. `static/webhook-forms.js`
- Form submission handlers
- Request/response display logic
- Helper functions for UI interactions
- Prevents page reloads on form submission

### 5. `static/admin-webhooks.js` (existing)
- Dynamic user/staff select population
- Auto-fill functionality

## Adding New Webhook Forms

To add a new webhook form:

1. **Add HTML form** in `templates/admin_webhooks.html`:
```html
<div class="webhook-card">
    <h2>N. Webhook Name</h2>
    <div class="endpoint">POST /webhooks/endpoint_name</div>
    <div class="webhook-description">
        <strong>Назначение:</strong> Description
    </div>
    <form id="form-webhook-name">
        <!-- Form fields -->
        <button type="submit" class="btn">Отправить запрос</button>
    </form>
    <div class="request-preview" id="request-preview-webhook-name">
        <h4>📤 Запрос:</h4>
        <pre id="request-data-webhook-name"></pre>
    </div>
    <div class="response" id="response-webhook-name"></div>
</div>
```

2. **Add form handler** in `static/webhook-forms.js`:
```javascript
// In initializeFormHandlers() function
const formWebhookName = document.getElementById('form-webhook-name');
if (formWebhookName) {
    formWebhookName.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);
        
        const payload = {
            // Build payload from form data
        };
        
        await sendWebhookRequestWithPreview('webhook-name', '/webhooks/endpoint_name', payload);
    });
}
```

3. **Test** the new form in the browser

## Benefits of This Structure

1. **Maintainability**: Each concern is in its own file
2. **Scalability**: Easy to add new forms without touching Python code
3. **Debugging**: Easier to find and fix issues
4. **Reusability**: CSS and JS can be shared across pages
5. **Version Control**: Cleaner diffs when making changes
6. **Performance**: Browser can cache static files

## Development Workflow

1. Edit HTML template for structure changes
2. Edit CSS for styling changes
3. Edit JS for behavior changes
4. Python file only needs changes for new configuration variables

## Testing

Access the admin panel at: `http://localhost:8453/admin/webhooks`

All forms should:
- Submit without page reload
- Show request preview
- Display response (success/error)
- Handle validation errors gracefully
