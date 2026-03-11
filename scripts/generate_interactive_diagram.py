"""
Generate interactive HTML ER diagram with D3.js visualization.

This script creates an interactive HTML page with:
- Zoomable/pannable ER diagram
- Clickable tables to show details
- Enum type reference
- Search functionality

Usage:
    python scripts/generate_interactive_diagram.py
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect
from database.models import Base, RegistrationStatus, SubscriptionStatus, KeyConflictStatus, \
    StaffRole, TicketType, TicketStatus, DeliveryMethod, SenderType, MessageType, FileType, \
    UploaderType, ActionType, WorkMode, EventType, EventStatus, RetryStatus, BroadcastStatus, \
    DeliveryStatus, EscalationType, SurveyType, ResolutionAction, SettingDataType, SettingCategory


def extract_schema_data() -> Dict[str, Any]:
    """Extract schema data from SQLAlchemy models."""
    
    tables = []
    relationships = []
    enums = {}
    
    # Extract enum data
    enum_classes = [
        ("RegistrationStatus", RegistrationStatus),
        ("SubscriptionStatus", SubscriptionStatus),
        ("KeyConflictStatus", KeyConflictStatus),
        ("StaffRole", StaffRole),
        ("TicketType", TicketType),
        ("TicketStatus", TicketStatus),
        ("DeliveryMethod", DeliveryMethod),
        ("SenderType", SenderType),
        ("MessageType", MessageType),
        ("FileType", FileType),
        ("UploaderType", UploaderType),
        ("ActionType", ActionType),
        ("WorkMode", WorkMode),
        ("EventType", EventType),
        ("EventStatus", EventStatus),
        ("RetryStatus", RetryStatus),
        ("BroadcastStatus", BroadcastStatus),
        ("DeliveryStatus", DeliveryStatus),
        ("EscalationType", EscalationType),
        ("SurveyType", SurveyType),
        ("ResolutionAction", ResolutionAction),
        ("SettingDataType", SettingDataType),
        ("SettingCategory", SettingCategory),
    ]
    
    for enum_name, enum_class in enum_classes:
        enums[enum_name] = [{"name": m.name, "value": m.value} for m in enum_class]
    
    # Extract table data
    for mapper in Base.registry.mappers:
        table_name = mapper.class_.__tablename__
        columns = []
        
        inspector = inspect(mapper.class_)
        for column in inspector.columns:
            col_data = {
                "name": column.name,
                "type": str(column.type),
                "primary_key": column.primary_key,
                "foreign_key": bool(column.foreign_keys),
                "nullable": column.nullable,
                "unique": column.unique,
            }
            
            # Extract foreign key target
            if column.foreign_keys:
                fk = list(column.foreign_keys)[0]
                col_data["fk_target"] = f"{fk.column.table.name}.{fk.column.name}"
                
                # Add relationship
                relationships.append({
                    "source": table_name,
                    "target": fk.column.table.name,
                    "source_column": column.name,
                    "target_column": fk.column.name,
                    "type": "one-to-one" if column.unique else "many-to-one"
                })
            
            columns.append(col_data)
        
        tables.append({
            "name": table_name,
            "columns": columns,
            "doc": mapper.class_.__doc__ or ""
        })
    
    return {
        "tables": tables,
        "relationships": relationships,
        "enums": enums
    }


def generate_html_diagram(schema_data: Dict[str, Any]) -> str:
    """Generate interactive HTML diagram."""
    
    html_template = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ER Диаграмма БД - I-TAT Bot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            overflow: hidden;
        }
        
        #header {
            background: white;
            padding: 15px 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 1000;
            position: relative;
        }
        
        #header h1 {
            font-size: 20px;
            color: #333;
        }
        
        #controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .btn {
            padding: 8px 16px;
            background: #1976d2;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            white-space: nowrap;
        }
        
        .btn:hover {
            background: #1565c0;
        }
        
        #search {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            width: 250px;
        }
        
        #diagram-container {
            width: 100vw;
            height: calc(100vh - 60px);
            position: relative;
            overflow: hidden;
            cursor: grab;
        }
        
        #diagram-container.dragging {
            cursor: grabbing;
        }
        
        #diagram-wrapper {
            position: absolute;
            transform-origin: 0 0;
            transition: transform 0.1s ease-out;
        }
        
        #sidebar {
            position: fixed;
            right: -400px;
            top: 60px;
            width: 400px;
            height: calc(100vh - 60px);
            background: white;
            box-shadow: -2px 0 8px rgba(0,0,0,0.1);
            transition: right 0.3s;
            overflow-y: auto;
            z-index: 999;
            padding: 20px;
        }
        
        #sidebar.open {
            right: 0;
        }
        
        #sidebar h2 {
            color: #1976d2;
            margin-bottom: 15px;
            font-size: 18px;
        }
        
        #sidebar h3 {
            color: #333;
            margin-top: 20px;
            margin-bottom: 10px;
            font-size: 16px;
        }
        
        .column-list {
            list-style: none;
        }
        
        .column-item {
            padding: 8px;
            margin: 4px 0;
            background: #f5f5f5;
            border-radius: 4px;
            font-size: 13px;
        }
        
        .column-name {
            font-weight: 600;
            color: #1976d2;
        }
        
        .column-type {
            color: #666;
            font-family: monospace;
        }
        
        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            margin-left: 5px;
        }
        
        .badge-pk {
            background: #4caf50;
            color: white;
        }
        
        .badge-fk {
            background: #ff9800;
            color: white;
        }
        
        .badge-uk {
            background: #2196f3;
            color: white;
        }
        
        .table-node {
            background: white;
            border: 2px solid #1976d2;
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            min-width: 200px;
            position: absolute;
            transition: box-shadow 0.2s, transform 0.2s;
        }
        
        .table-node:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            transform: translateY(-2px);
            z-index: 10;
        }
        
        .table-name {
            font-weight: 600;
            color: #1976d2;
            font-size: 14px;
            margin-bottom: 8px;
            border-bottom: 1px solid #e0e0e0;
            padding-bottom: 4px;
        }
        
        .table-columns {
            font-size: 12px;
            color: #666;
        }
        
        .enum-section {
            margin-top: 20px;
        }
        
        .enum-item {
            background: #f5f5f5;
            padding: 8px;
            margin: 4px 0;
            border-radius: 4px;
            font-size: 13px;
        }
        
        .enum-value {
            font-family: monospace;
            color: #1976d2;
        }
        
        #close-sidebar {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #f44336;
            color: white;
            border: none;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            cursor: pointer;
            font-size: 18px;
            line-height: 1;
        }
        
        #zoom-info {
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            z-index: 1000;
        }
    </style>
</head>
<body>
    <div id="header">
        <h1>📊 ER Диаграмма БД - I-TAT Bot</h1>
        <div id="controls">
            <input type="text" id="search" placeholder="Поиск таблиц...">
            <button class="btn" onclick="showEnums()">📋 Enum типы</button>
            <button class="btn" onclick="resetZoom()">🔍 Сбросить</button>
        </div>
    </div>
    
    <div id="diagram-container">
        <div id="diagram-wrapper"></div>
    </div>
    
    <div id="zoom-info">
        Масштаб: <span id="zoom-value">100%</span> | Используйте колесо мыши для зума, перетаскивайте для навигации
    </div>
    
    <div id="sidebar">
        <button id="close-sidebar" onclick="closeSidebar()">×</button>
        <div id="sidebar-content"></div>
    </div>
    
    <script>
        const schemaData = """ + json.dumps(schema_data, ensure_ascii=False) + """;
        
        let currentZoom = 1;
        let currentX = 0;
        let currentY = 0;
        let isDragging = false;
        let startX, startY;
        
        function renderDiagram() {
            const wrapper = document.getElementById('diagram-wrapper');
            wrapper.innerHTML = '';
            
            // Simple grid layout
            const tables = schemaData.tables;
            const cols = Math.ceil(Math.sqrt(tables.length));
            const cellWidth = 250;
            const cellHeight = 200;
            
            tables.forEach((table, index) => {
                const row = Math.floor(index / cols);
                const col = index % cols;
                
                const node = document.createElement('div');
                node.className = 'table-node';
                node.style.left = (col * cellWidth + 50) + 'px';
                node.style.top = (row * cellHeight + 50) + 'px';
                
                const nameDiv = document.createElement('div');
                nameDiv.className = 'table-name';
                nameDiv.textContent = table.name;
                node.appendChild(nameDiv);
                
                const columnsDiv = document.createElement('div');
                columnsDiv.className = 'table-columns';
                columnsDiv.textContent = `${table.columns.length} колонок`;
                node.appendChild(columnsDiv);
                
                node.onclick = (e) => {
                    e.stopPropagation();
                    showTableDetails(table);
                };
                
                wrapper.appendChild(node);
            });
        }
        
        function showTableDetails(table) {
            const sidebar = document.getElementById('sidebar');
            const content = document.getElementById('sidebar-content');
            
            let html = `<h2>${table.name}</h2>`;
            
            html += '<h3>Колонки</h3><ul class="column-list">';
            
            table.columns.forEach(col => {
                html += '<li class="column-item">';
                html += `<span class="column-name">${col.name}</span>`;
                html += `<span class="column-type"> : ${col.type}</span>`;
                
                if (col.primary_key) html += '<span class="badge badge-pk">PK</span>';
                if (col.foreign_key) html += '<span class="badge badge-fk">FK</span>';
                if (col.unique && !col.primary_key) html += '<span class="badge badge-uk">UK</span>';
                
                if (col.fk_target) {
                    html += `<br><small style="color: #999;">→ ${col.fk_target}</small>`;
                }
                
                html += '</li>';
            });
            
            html += '</ul>';
            
            content.innerHTML = html;
            sidebar.classList.add('open');
        }
        
        function showEnums() {
            const sidebar = document.getElementById('sidebar');
            const content = document.getElementById('sidebar-content');
            
            let html = '<h2>📋 Enum типы</h2>';
            
            Object.keys(schemaData.enums).forEach(enumName => {
                html += `<div class="enum-section"><h3>${enumName}</h3>`;
                
                schemaData.enums[enumName].forEach(member => {
                    html += `<div class="enum-item">`;
                    html += `<span class="enum-value">${member.value}</span>`;
                    html += ` <span style="color: #999;">(${member.name})</span>`;
                    html += `</div>`;
                });
                
                html += '</div>';
            });
            
            content.innerHTML = html;
            sidebar.classList.add('open');
        }
        
        function closeSidebar() {
            document.getElementById('sidebar').classList.remove('open');
        }
        
        function resetZoom() {
            currentZoom = 1;
            currentX = 0;
            currentY = 0;
            updateTransform();
        }
        
        function updateTransform() {
            const wrapper = document.getElementById('diagram-wrapper');
            wrapper.style.transform = `translate(${currentX}px, ${currentY}px) scale(${currentZoom})`;
            document.getElementById('zoom-value').textContent = Math.round(currentZoom * 100) + '%';
        }
        
        // Search functionality
        document.getElementById('search').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const nodes = document.querySelectorAll('.table-node');
            
            nodes.forEach(node => {
                const tableName = node.querySelector('.table-name').textContent.toLowerCase();
                if (tableName.includes(query)) {
                    node.style.display = 'block';
                    node.style.opacity = '1';
                } else {
                    node.style.opacity = '0.3';
                }
            });
        });
        
        // Pan and zoom
        const container = document.getElementById('diagram-container');
        
        container.addEventListener('mousedown', (e) => {
            if (e.target === container || e.target.id === 'diagram-wrapper') {
                isDragging = true;
                container.classList.add('dragging');
                startX = e.clientX - currentX;
                startY = e.clientY - currentY;
                e.preventDefault();
            }
        });
        
        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                currentX = e.clientX - startX;
                currentY = e.clientY - startY;
                updateTransform();
            }
        });
        
        document.addEventListener('mouseup', () => {
            isDragging = false;
            container.classList.remove('dragging');
        });
        
        container.addEventListener('wheel', (e) => {
            e.preventDefault();
            
            // Get mouse position relative to container
            const rect = container.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            // Calculate position in diagram space before zoom
            const beforeZoomX = (mouseX - currentX) / currentZoom;
            const beforeZoomY = (mouseY - currentY) / currentZoom;
            
            // Update zoom
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newZoom = currentZoom * delta;
            currentZoom = Math.max(0.1, Math.min(3, newZoom));
            
            // Calculate position in diagram space after zoom
            const afterZoomX = beforeZoomX * currentZoom;
            const afterZoomY = beforeZoomY * currentZoom;
            
            // Adjust pan to keep mouse position stable
            currentX = mouseX - afterZoomX;
            currentY = mouseY - afterZoomY;
            
            updateTransform();
        }, { passive: false });
        
        // Initial render
        renderDiagram();
        updateTransform();
    </script>
</body>
</html>
""".strip()
    
    return html_template


def main():
    """Generate interactive HTML diagram."""
    
    output_dir = project_root / "docs" / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("🔧 Extracting schema data...")
    schema_data = extract_schema_data()
    
    print("🔧 Generating interactive HTML diagram...")
    html_content = generate_html_diagram(schema_data)
    
    html_file = output_dir / "er_diagram_interactive.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ Generated interactive diagram: {html_file}")
    print("\n📊 Generation complete!")
    print(f"📁 Output directory: {output_dir}")
    print(f"\n💡 Open in browser: file://{html_file.absolute()}")


if __name__ == "__main__":
    main()
