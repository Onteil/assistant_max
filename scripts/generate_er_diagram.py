"""
Generate ER diagram from SQLAlchemy models.

This script creates an interactive ER diagram showing:
- All database tables and their relationships
- Enum types used in the schema
- Foreign key relationships
- Table columns with types

Requirements:
    pip install eralchemy2 pygraphviz

Usage:
    python scripts/generate_er_diagram.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from eralchemy2 import render_er
from database.models import Base


def generate_er_diagram():
    """Generate ER diagram from SQLAlchemy models."""
    
    output_dir = project_root / "docs" / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate different formats
    formats = {
        "png": output_dir / "er_diagram.png",
        "pdf": output_dir / "er_diagram.pdf",
        "dot": output_dir / "er_diagram.dot",
    }
    
    print("🔧 Generating ER diagrams from SQLAlchemy models...")
    
    for format_name, output_path in formats.items():
        try:
            render_er(Base, str(output_path))
            print(f"✅ Generated {format_name.upper()}: {output_path}")
        except Exception as e:
            print(f"❌ Failed to generate {format_name.upper()}: {e}")
    
    print("\n📊 ER diagram generation complete!")
    print(f"📁 Output directory: {output_dir}")


if __name__ == "__main__":
    generate_er_diagram()
