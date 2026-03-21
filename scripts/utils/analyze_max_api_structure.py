"""
Анализ структуры MAX API без выполнения запросов.

Этот скрипт анализирует доступные методы maxapi.Bot и создает документацию.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import get_type_hints

from maxapi import Bot


def analyze_bot_methods():
    """Анализ всех методов Bot класса."""
    methods_info = []
    
    # Получаем все методы класса Bot
    for name, method in inspect.getmembers(Bot, predicate=inspect.isfunction):
        if name.startswith('_'):
            continue
        
        # Получаем сигнатуру метода
        try:
            sig = inspect.signature(method)
            params = []
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                param_info = {
                    'name': param_name,
                    'type': str(param.annotation) if param.annotation != inspect.Parameter.empty else 'Any',
                    'default': str(param.default) if param.default != inspect.Parameter.empty else 'Required',
                    'required': param.default == inspect.Parameter.empty
                }
                params.append(param_info)
            
            # Получаем docstring
            docstring = inspect.getdoc(method) or "Документация отсутствует"
            
            method_info = {
                'name': name,
                'parameters': params,
                'return_type': str(sig.return_annotation) if sig.return_annotation != inspect.Signature.empty else 'Any',
                'docstring': docstring,
                'is_async': inspect.iscoroutinefunction(method)
            }
            
            methods_info.append(method_info)
        except Exception as e:
            print(f"Ошибка при анализе метода {name}: {e}")
    
    return sorted(methods_info, key=lambda x: x['name'])


def categorize_methods(methods):
    """Категоризация методов по функциональности."""
    categories = {
        'Информация о боте': [],
        'Отправка сообщений': [],
        'Редактирование сообщений': [],
        'Удаление': [],
        'Получение данных': [],
        'Работа с чатами': [],
        'Работа с участниками': [],
        'Закрепленные сообщения': [],
        'Загрузка файлов': [],
        'Вебхуки и подписки': [],
        'Команды': [],
        'Действия': [],
        'Прочее': []
    }
    
    for method in methods:
        name = method['name']
        
        if 'me' in name and 'from' not in name:
            categories['Информация о боте'].append(method)
        elif name.startswith('send_'):
            categories['Отправка сообщений'].append(method)
        elif name.startswith('edit_'):
            categories['Редактирование сообщений'].append(method)
        elif name.startswith('delete_'):
            categories['Удаление'].append(method)
        elif name.startswith('get_'):
            categories['Получение данных'].append(method)
        elif 'chat' in name and not name.startswith('get_'):
            categories['Работа с чатами'].append(method)
        elif 'member' in name or 'admin' in name or 'kick' in name:
            categories['Работа с участниками'].append(method)
        elif 'pin' in name:
            categories['Закрепленные сообщения'].append(method)
        elif 'upload' in name or 'file' in name:
            categories['Загрузка файлов'].append(method)
        elif 'webhook' in name or 'subscription' in name:
            categories['Вебхуки и подписки'].append(method)
        elif 'command' in name:
            categories['Команды'].append(method)
        elif 'action' in name or 'marker' in name:
            categories['Действия'].append(method)
        else:
            categories['Прочее'].append(method)
    
    # Удаляем пустые категории
    return {k: v for k, v in categories.items() if v}


def generate_markdown_report(categorized_methods):
    """Генерация Markdown отчета."""
    lines = [
        "# MAX API - Полный справочник методов",
        "",
        f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Оглавление",
        ""
    ]
    
    # Оглавление
    for category in categorized_methods.keys():
        anchor = category.lower().replace(' ', '-')
        lines.append(f"- [{category}](#{anchor})")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Детальное описание по категориям
    for category, methods in categorized_methods.items():
        lines.append(f"## {category}")
        lines.append("")
        lines.append(f"Всего методов: {len(methods)}")
        lines.append("")
        
        for method in methods:
            lines.append(f"### `{method['name']}`")
            lines.append("")
            
            # Async/sync
            if method['is_async']:
                lines.append("**Тип:** Асинхронный метод")
            else:
                lines.append("**Тип:** Синхронный метод")
            lines.append("")
            
            # Описание
            lines.append("**Описание:**")
            lines.append(f"> {method['docstring']}")
            lines.append("")
            
            # Параметры
            if method['parameters']:
                lines.append("**Параметры:**")
                lines.append("")
                lines.append("| Параметр | Тип | Обязательный | Значение по умолчанию |")
                lines.append("|----------|-----|--------------|----------------------|")
                
                for param in method['parameters']:
                    required = "✅ Да" if param['required'] else "❌ Нет"
                    default = param['default'] if not param['required'] else "-"
                    lines.append(f"| `{param['name']}` | `{param['type']}` | {required} | `{default}` |")
                
                lines.append("")
            else:
                lines.append("**Параметры:** Нет")
                lines.append("")
            
            # Возвращаемое значение
            lines.append(f"**Возвращает:** `{method['return_type']}`")
            lines.append("")
            
            # Пример использования
            lines.append("**Пример использования:**")
            lines.append("")
            lines.append("```python")
            
            if method['is_async']:
                params_str = ", ".join([f"{p['name']}=..." for p in method['parameters'][:3]])
                if len(method['parameters']) > 3:
                    params_str += ", ..."
                lines.append(f"result = await bot.{method['name']}({params_str})")
            else:
                lines.append(f"result = bot.{method['name']}()")
            
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")
    
    return "\n".join(lines)


def generate_json_report(methods):
    """Генерация JSON отчета."""
    return json.dumps(methods, ensure_ascii=False, indent=2)


def generate_summary_table(categorized_methods):
    """Генерация сводной таблицы."""
    lines = [
        "# MAX API - Сводная таблица методов",
        "",
        f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Статистика",
        ""
    ]
    
    total = sum(len(methods) for methods in categorized_methods.values())
    lines.append(f"**Всего методов:** {total}")
    lines.append("")
    
    lines.append("| Категория | Количество методов |")
    lines.append("|-----------|-------------------|")
    
    for category, methods in categorized_methods.items():
        lines.append(f"| {category} | {len(methods)} |")
    
    lines.append("")
    lines.append("## Быстрый справочник")
    lines.append("")
    lines.append("| Метод | Категория | Async | Параметров |")
    lines.append("|-------|-----------|-------|-----------|")
    
    for category, methods in categorized_methods.items():
        for method in methods:
            async_mark = "✅" if method['is_async'] else "❌"
            param_count = len(method['parameters'])
            lines.append(f"| `{method['name']}` | {category} | {async_mark} | {param_count} |")
    
    return "\n".join(lines)


def main():
    """Главная функция."""
    print("🔍 Анализ структуры MAX API...")
    
    # Анализируем методы
    methods = analyze_bot_methods()
    print(f"✅ Найдено методов: {len(methods)}")
    
    # Категоризируем
    categorized = categorize_methods(methods)
    print(f"✅ Категорий: {len(categorized)}")
    
    # Создаем директорию для отчетов
    reports_dir = Path("api_analysis")
    reports_dir.mkdir(exist_ok=True)
    
    # Генерируем отчеты
    print("\n📝 Генерация отчетов...")
    
    # 1. Полный Markdown отчет
    markdown_report = generate_markdown_report(categorized)
    markdown_file = reports_dir / "MAX_API_FULL_REFERENCE.md"
    markdown_file.write_text(markdown_report, encoding='utf-8')
    print(f"✅ Создан: {markdown_file}")
    
    # 2. Сводная таблица
    summary_table = generate_summary_table(categorized)
    summary_file = reports_dir / "MAX_API_SUMMARY.md"
    summary_file.write_text(summary_table, encoding='utf-8')
    print(f"✅ Создан: {summary_file}")
    
    # 3. JSON отчет
    json_report = generate_json_report(methods)
    json_file = reports_dir / "MAX_API_METHODS.json"
    json_file.write_text(json_report, encoding='utf-8')
    print(f"✅ Создан: {json_file}")
    
    print("\n" + "─" * 5)
    print("СВОДКА")
    print("─" * 5)
    print(f"\n📊 Всего методов: {len(methods)}")
    print(f"📁 Категорий: {len(categorized)}")
    print("\nРаспределение по категориям:")
    for category, methods_list in categorized.items():
        print(f"  • {category}: {len(methods_list)} методов")
    
    print(f"\n📂 Отчеты сохранены в: {reports_dir.absolute()}")
    print("\n✨ Анализ завершен!")


if __name__ == "__main__":
    main()
