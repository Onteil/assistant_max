"""
Admin Panel for Testing Webhooks

Simple web interface for testing all webhook endpoints.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
import os
from pathlib import Path

router = APIRouter()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="api/templates")

# Get configuration from environment
WEBHOOK_HOST = os.getenv("HOST", "http://localhost:8453")
# WEBHOOK_HOST = "https://assistant.i-tat.ru"
WEBHOOK_PATH_MAX = os.getenv("WEBHOOK_PATH_MAX", "/max/webhook")
WEBHOOK_PATH_MAIN = os.getenv("WEBHOOK_PATH_MAIN", "/max/webhook")
API_PREFIX = "/bot/api"
API_KEY = "mJNc4TQdzd5eVNh3ygtMvdcmggxCX58uK2kVNPr3CYI"


@router.get("/admin/webhooks", response_class=HTMLResponse)
async def webhook_admin_panel(request: Request):
    """
    Admin panel for testing webhook endpoints.
    All webhooks on one page with forms for each endpoint.
    """
    return templates.TemplateResponse(
        "admin_webhooks.html",
        {
            "request": request,
            "WEBHOOK_HOST": WEBHOOK_HOST,
            "WEBHOOK_PATH_MAX": WEBHOOK_PATH_MAX,
            "API_PREFIX": API_PREFIX,
            "API_KEY": API_KEY,
        }
    )


@router.get("/admin/er-diagram", response_class=HTMLResponse)
async def view_er_diagram(request: Request):
    """
    Display interactive ER diagram.
    Serves the pre-generated HTML template.
    """
    return templates.TemplateResponse(
        "er_diagram.html",
        {"request": request}
    )


@router.get("/admin/database-enums", response_class=HTMLResponse)
async def view_database_enums(request: Request):
    """
    Display database enum types documentation.
    """
    import sys
    import json
    from pathlib import Path
    
    # Add project root to path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Import enum extraction function
    from scripts.generate_interactive_diagram import extract_schema_data
    
    schema_data = extract_schema_data()
    enums_json = json.dumps(schema_data['enums'], ensure_ascii=False)
    
    return templates.TemplateResponse(
        "database_enums.html",
        {
            "request": request,
            "enums_json": enums_json
        }
    )


@router.get("/admin/generate-er-diagram")
async def generate_er_diagram():
    """
    Generate ER diagram on-demand and return HTML.
    This endpoint regenerates the diagram from current models.
    """
    import sys
    from pathlib import Path
    
    # Add project root to path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Import and run the generator
    from scripts.generate_interactive_diagram import extract_schema_data, generate_html_diagram
    
    schema_data = extract_schema_data()
    html_content = generate_html_diagram(schema_data)
    
    # Save to templates directory for future use
    template_path = project_root / "api" / "templates" / "er_diagram.html"
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return HTMLResponse(content=html_content)
