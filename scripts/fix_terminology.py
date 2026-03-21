"""
Script to fix terminology in MAX bot handlers.
Replaces inline main menu text with constant from texts.py
"""

import re
from pathlib import Path

# Old text pattern (with variations)
OLD_TEXT_PATTERN = r'''main_menu_text = \(
            "🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>\\n\\n"
            "Здесь вы можете:\\n\\n"
            "💰 <b>Получить счёт</b> — запросить счет на оплату лицензии ГРАНД-Сметы\\n"
            "🆘 <b>Техподдержка</b> — получить помощь по работе с программой\\n"
            "🔄 <b>Продление</b> — продлить лицензию на ГРАНД-Смету\\n"
            "🗃️ <b>Архив обращений</b> — просмотреть историю ваших обращений\\n"
            "👤 <b>Мой профиль</b> — управление вашими данными и настройками\\n\\n"'''

OLD_TEXT_PATTERN2 = r'''welcome_text = \(
                "🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>\\n\\n"
                "Здесь вы можете:\\n\\n"
                "💰 <b>Получить счёт</b> — запросить счет на оплату лицензии ГРАНД-Сметы\\n"
                "🆘 <b>Техподдержка</b> — получить помощь по работе с программой\\n"
                "🔄 <b>Продление</b> — продлить лицензию на ГРАНД-Смету\\n"
                "🗃️ <b>Архив обращений</b> — просмотреть историю ваших обращений\\n"
                "👤 <b>Мой профиль</b> — управление вашими данными и настройками\\n\\n"'''

# Files to fix
FILES_TO_FIX = [
    "bots/max_bot/handlers/user/archive.py",
    "bots/max_bot/handlers/user/active_tickets.py",
    "bots/max_bot/handlers/tickets/support.py",
    "bots/max_bot/handlers/tickets/invoice.py",
]

def fix_file(filepath: str):
    """Fix terminology in a single file."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return
    
    content = path.read_text(encoding='utf-8')
    original_content = content
    
    # Check if MAX_MAIN_MENU_TEXT import exists
    if 'from bots.max_bot.texts import' not in content:
        print(f"Skipping {filepath} - no imports from texts.py")
        return
    
    # Add MAX_MAIN_MENU_TEXT to imports if not present
    if 'MAX_MAIN_MENU_TEXT' not in content:
        # Find the import line and add MAX_MAIN_MENU_TEXT
        import_pattern = r'(from bots\.max_bot\.texts import[^\n]+)'
        match = re.search(import_pattern, content)
        if match:
            old_import = match.group(1)
            if old_import.endswith(')'):
                # Multi-line import
                new_import = old_import.replace(')', ', MAX_MAIN_MENU_TEXT)')
            else:
                # Single line import
                new_import = old_import + ', MAX_MAIN_MENU_TEXT'
            content = content.replace(old_import, new_import)
            print(f"Added MAX_MAIN_MENU_TEXT to imports in {filepath}")
    
    # Replace inline text with constant
    # Pattern 1: main_menu_text = (...)
    pattern1 = r'main_menu_text = \(\s*"🎉[^)]+\)'
    if re.search(pattern1, content):
        content = re.sub(pattern1, 'main_menu_text = MAX_MAIN_MENU_TEXT', content)
        print(f"Replaced main_menu_text in {filepath}")
    
    # Pattern 2: welcome_text = (...)
    pattern2 = r'welcome_text = \(\s*"🎉[^)]+\)'
    if re.search(pattern2, content):
        content = re.sub(pattern2, 'welcome_text = MAX_MAIN_MENU_TEXT', content)
        print(f"Replaced welcome_text in {filepath}")
    
    if content != original_content:
        path.write_text(content, encoding='utf-8')
        print(f"✅ Fixed {filepath}")
    else:
        print(f"⏭️  No changes needed in {filepath}")

def main():
    print("Fixing terminology in MAX bot handlers...")
    print("─" * 5)
    
    for filepath in FILES_TO_FIX:
        fix_file(filepath)
        print()
    
    print("─" * 5)
    print("Done!")

if __name__ == "__main__":
    main()
