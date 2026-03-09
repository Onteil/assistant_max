"""
Generate Mermaid ER diagram from SQLAlchemy models.

This script creates a Mermaid.js ER diagram that can be:
- Viewed in GitHub/GitLab markdown
- Rendered in documentation sites
- Converted to images using mermaid-cli

Usage:
    python scripts/generate_mermaid_diagram.py
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
import enum

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect
from sqlalchemy.orm import RelationshipProperty
from database.models import Base, RegistrationStatus, SubscriptionStatus, KeyConflictStatus, \
    StaffRole, TicketType, TicketStatus, DeliveryMethod, SenderType, MessageType, FileType, \
    UploaderType, ActionType, WorkMode, EventType, EventStatus, RetryStatus, BroadcastStatus, \
    DeliveryStatus, EscalationType, SurveyType, ResolutionAction, SettingDataType, SettingCategory


def get_column_type(column) -> str:
    """Get simplified column type for display."""
    col_type = str(column.type)
    
    # Simplify common types
    if "VARCHAR" in col_type or "TEXT" in col_type:
        return "String"
    elif "BIGINT" in col_type:
        return "BigInteger"
    elif "INTEGER" in col_type:
        return "Integer"
    elif "BOOLEAN" in col_type:
        return "Boolean"
    elif "DATETIME" in col_type:
        return "DateTime"
    elif "DATE" in col_type:
        return "Date"
    elif "TIME" in col_type:
        return "Time"
    elif "JSON" in col_type:
        return "JSON"
    elif "ENUM" in col_type:
        # Extract enum name
        return col_type.split("(")[1].split(")")[0] if "(" in col_type else "Enum"
    
    return col_type


def generate_mermaid_er() -> str:
    """Generate Mermaid ER diagram syntax."""
    
    lines = [
        "erDiagram",
        ""
    ]
    
    # Track relationships to avoid duplicates
    relationships_added = set()
    
    # Generate tables
    for mapper in Base.registry.mappers:
        table_name = mapper.class_.__tablename__
        lines.append(f"    {table_name} {{")
        
        # Add columns
        inspector = inspect(mapper.class_)
        for column in inspector.columns:
            col_name = column.name
            col_type = get_column_type(column)
            
            # Add constraints
            constraints = []
            if column.primary_key:
                constraints.append("PK")
            if column.foreign_keys:
                constraints.append("FK")
            if column.unique and not column.primary_key:
                constraints.append("UK")
            if not column.nullable and not column.primary_key:
                constraints.append("NOT NULL")
            
            constraint_str = f" {','.join(constraints)}" if constraints else ""
            lines.append(f"        {col_type} {col_name}{constraint_str}")
        
        lines.append("    }")
        lines.append("")
    
    # Generate relationships
    for mapper in Base.registry.mappers:
        table_name = mapper.class_.__tablename__
        
        # Foreign key relationships
        inspector = inspect(mapper.class_)
        for column in inspector.columns:
            if column.foreign_keys:
                for fk in column.foreign_keys:
                    target_table = fk.column.table.name
                    rel_key = f"{table_name}-{target_table}"
                    
                    if rel_key not in relationships_added:
                        # Determine cardinality
                        if column.unique:
                            cardinality = "||--||"  # One-to-one
                        else:
                            cardinality = "}o--||"  # Many-to-one
                        
                        lines.append(f"    {table_name} {cardinality} {target_table} : \"has\"")
                        relationships_added.add(rel_key)
    
    return "\n".join(lines)


def generate_enum_documentation() -> str:
    """Generate markdown documentation for all enum types."""
    
    enums = [
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
    
    lines = [
        "# Database Enum Types",
        "",
        "This document lists all enum types used in the database schema.",
        ""
    ]
    
    for enum_name, enum_class in enums:
        lines.append(f"## {enum_name}")
        lines.append("")
        lines.append("| Value | Description |")
        lines.append("|-------|-------------|")
        
        for member in enum_class:
            lines.append(f"| `{member.value}` | {member.name} |")
        
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Generate ER diagram and enum documentation."""
    
    output_dir = project_root / "docs" / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("🔧 Generating Mermaid ER diagram...")
    
    # Generate Mermaid diagram
    mermaid_content = generate_mermaid_er()
    mermaid_file = output_dir / "er_diagram.mmd"
    
    with open(mermaid_file, "w", encoding="utf-8") as f:
        f.write(mermaid_content)
    
    print(f"✅ Generated Mermaid diagram: {mermaid_file}")
    
    # Generate markdown with embedded diagram
    markdown_file = output_dir / "er_diagram.md"
    with open(markdown_file, "w", encoding="utf-8") as f:
        f.write("# Database ER Diagram\n\n")
        f.write("```mermaid\n")
        f.write(mermaid_content)
        f.write("\n```\n")
    
    print(f"✅ Generated Markdown diagram: {markdown_file}")
    
    # Generate enum documentation
    print("\n🔧 Generating enum documentation...")
    enum_content = generate_enum_documentation()
    enum_file = output_dir / "database_enums.md"
    
    with open(enum_file, "w", encoding="utf-8") as f:
        f.write(enum_content)
    
    print(f"✅ Generated enum documentation: {enum_file}")
    
    print("\n📊 Generation complete!")
    print(f"📁 Output directory: {output_dir}")
    print("\n💡 To view the diagram:")
    print("   - Open er_diagram.md in GitHub/GitLab")
    print("   - Use Mermaid Live Editor: https://mermaid.live")
    print("   - Install mermaid-cli: npm install -g @mermaid-js/mermaid-cli")
    print("   - Convert to image: mmdc -i er_diagram.mmd -o er_diagram.png")


if __name__ == "__main__":
    main()
