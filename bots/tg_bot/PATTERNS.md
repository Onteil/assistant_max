# Паттерны и Лучшие Практики Telegram Bot

Этот документ описывает основные паттерны и практики, выделенные из исходного кода.

## 📁 Структура Проекта

```
bots/tg_bot/
├── __init__.py              # Экспорт главного роутера
├── callback_datas.py        # CallbackData фабрики
├── states.py                # FSM состояния
├── shortcuts.py             # Вспомогательные функции
├── utils.py                 # Утилиты общего назначения
├── handlers/
│   ├── __init__.py          # Объединение всех роутеров
│   ├── commands.py          # Обработчики команд
│   ├── callbacks.py         # Обработчики callback запросов
│   └── messages.py          # Обработчики сообщений
└── keyboards/
    ├── __init__.py          # Экспорт функций клавиатур
    ├── inline_kb.py         # Inline клавиатуры
    └── reply_kb.py          # Reply клавиатуры
```

## 🎯 Основные Паттерны

### 1. Модульная Организация Handlers

**Принцип:** Разделяйте обработчики по типам в отдельные модули.

```python
# handlers/__init__.py
from aiogram import Router
from .commands import router as commands_router
from .callbacks import router as callbacks_router
from .messages import router as messages_router

tg_bot_router = Router(name="tg_bot_main")
tg_bot_router.include_routers(
    commands_router,
    callbacks_router,
    messages_router
)
```

**Преимущества:**
- Легко найти нужный обработчик
- Простое масштабирование
- Изолированная логика

---

### 2. Type-Safe Callback Data

**Принцип:** Используйте CallbackData фабрики вместо строк.

```python
class ItemCallback(CallbackData, prefix="item"):
    action: str
    item_id: int | None = None
    page: int | None = None

# Использование
@router.callback_query(ItemCallback.filter(F.action == "select"))
async def process_selection(call: CallbackQuery, callback_data: ItemCallback):
    item_id = callback_data.item_id  # Type-safe!
```

**Преимущества:**
- Автокомплит в IDE
- Защита от опечаток
- Валидация данных

---

### 3. Пагинация с Переиспользуемыми Функциями

**Принцип:** Создавайте универсальные функции для пагинации.

```python
async def create_paginated_keyboard(
    items: list[dict],
    page: int = 0,
    callback_factory=ItemCallback,
    items_per_page: int = 10
):
    builder = InlineKeyboardBuilder()
    
    # Логика пагинации
    total_pages = math.ceil(len(items) / items_per_page)
    start = page * items_per_page
    end = start + items_per_page
    
    # Кнопки элементов
    for item in items[start:end]:
        builder.button(
            text=item['name'],
            callback_data=callback_factory(action="select", item_id=item['id'])
        )
    
    # Навигация
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(text="⬅️", ...)
            )
        pagination_row.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(text="➡️", ...)
            )
        builder.row(*pagination_row)
    
    return builder.as_markup()
```

**Ключевые элементы:**
- Константы для размеров страниц
- Кнопка "noop" для индикатора
- Условная отрисовка стрелок

---

### 4. FSM States Группировка

**Принцип:** Группируйте состояния по функциональным блокам.

```python
class RegistrationStates(StatesGroup):
    """Состояния для процесса регистрации."""
    waiting_for_name = State()
    waiting_for_email = State()
    waiting_for_confirmation = State()

class FormStates(StatesGroup):
    """Состояния для заполнения формы."""
    waiting_for_input = State()
    waiting_for_file = State()
```

**Преимущества:**
- Логическая группировка
- Легко понять флоу
- Простое управление

---

### 5. Обработка Callbacks с Немедленным Ответом

**Принцип:** Всегда вызывайте `call.answer()` в начале обработчика.

```python
@router.callback_query(ItemCallback.filter(F.action == "view"))
async def process_pagination(call: CallbackQuery, callback_data: ItemCallback):
    await call.answer()  # Убирает "часики" у пользователя
    
    # Остальная логика...
```

**Важно:**
- Вызывайте в начале функции
- Используйте `show_alert=True` для важных уведомлений
- Обрабатывайте TelegramBadRequest

---

### 6. Обработка Ошибок при Редактировании Сообщений

**Принцип:** Сообщение может быть удалено, обрабатывайте исключения.

```python
try:
    await call.message.edit_text(text, reply_markup=keyboard)
except TelegramBadRequest as e:
    logger.warning(f"Failed to edit message: {e}")
    # Отправляем новое сообщение вместо редактирования
    await call.message.answer(text, reply_markup=keyboard)
```

---

### 7. Параллельное Выполнение Задач

**Принцип:** Запускайте независимые задачи параллельно.

```python
# Fire and forget для медленных задач
asyncio.create_task(
    asyncio.to_thread(slow_external_service.log_activity, user)
)

# Ждем только критичные задачи
user = await db_service.get_user(session, user_id)
items = await db_service.get_items(session)
```

**Когда использовать:**
- Логирование в внешние сервисы
- Аналитика
- Некритичные операции

---

### 8. Анимация Загрузки

**Принцип:** Показывайте прогресс для долгих операций.

```python
async def animate_loading(message: Message, base_text: str):
    """Анимирует прогресс-бар в сообщении."""
    frames = [
        "⬜️⬜️⬜️⬜️⬜️⬜️",
        "🟦⬜️⬜️⬜️⬜️⬜️",
        "🟦🟦⬜️⬜️⬜️⬜️",
        # ...
    ]
    while True:
        for frame in frames:
            try:
                await message.edit_text(f"{base_text}\n\n{frame}")
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                return

# Использование
loading_message = await message.answer("⏳ Загрузка...")
progress_task = asyncio.create_task(animate_loading(loading_message, "⏳ Загрузка..."))

try:
    # Долгая операция
    result = await long_operation()
finally:
    progress_task.cancel()
    await asyncio.sleep(0.1)
```

---

### 9. Контекстная Навигация

**Принцип:** Сохраняйте контекст для умного возврата "Назад".

```python
class NavigationCallback(CallbackData, prefix="nav"):
    action: str
    from_section: str | None = None

# При переходе вперед
callback_data=NavigationCallback(
    action="forward",
    from_section="categories"
)

# При возврате
@router.callback_query(NavigationCallback.filter(F.action == "back"))
async def go_back(call: CallbackQuery, callback_data: NavigationCallback):
    from_section = callback_data.from_section
    # Восстанавливаем нужное меню
```

---

### 10. Валидация Входных Данных

**Принцип:** Проверяйте данные перед обработкой.

```python
@router.message(StateFilter(RegistrationStates.waiting_for_name), F.text)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    
    # Валидация
    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Попробуйте еще раз:")
        return
    
    if not name.replace(" ", "").isalpha():
        await message.answer("❌ Имя должно содержать только буквы:")
        return
    
    # Сохранение
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_for_email)
```

---

### 11. Логирование

**Принцип:** Логируйте важные события и ошибки.

```python
import logging

logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_command(message: Message):
    logger.info(f"User {message.from_user.id} started the bot")
    # ...

@router.callback_query(...)
async def some_handler(call: CallbackQuery):
    try:
        # Логика
        pass
    except Exception as e:
        logger.error(f"Error in handler: {e}", exc_info=True)
        await call.answer("Произошла ошибка", show_alert=True)
```

---

### 12. Работа с Медиагруппами

**Принцип:** Отправляйте несколько файлов одним сообщением.

```python
from aiogram.types import InputMediaDocument, BufferedInputFile

media_group = []
for i, file_bytes in enumerate(files):
    filename = f"document_{i+1}.pdf"
    file_to_send = BufferedInputFile(file_bytes, filename=filename)
    media_group.append(InputMediaDocument(media=file_to_send))

# Подпись только у первого элемента
media_group[0].caption = "Ваши документы готовы!"
media_group[0].parse_mode = "Markdown"

await message.answer_media_group(media=media_group)
```

---

## 🔧 Утилиты и Helpers

### Форматирование Текста

```python
def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезает текст до указанной длины."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
```

### Безопасное Удаление

```python
async def safe_delete_message(message: Message) -> bool:
    """Безопасно удаляет сообщение."""
    try:
        await message.delete()
        return True
    except Exception:
        return False
```

---

## 📝 Рекомендации

1. **Всегда используйте type hints** - помогает IDE и предотвращает ошибки
2. **Документируйте функции** - особенно публичные API
3. **Используйте константы** - для магических чисел и строк
4. **Обрабатывайте исключения** - Telegram API может вернуть ошибку
5. **Логируйте важные события** - упрощает отладку
6. **Тестируйте на разных сценариях** - особенно edge cases
7. **Используйте FSMContext** - для хранения временных данных
8. **Очищайте состояние** - при старте нового флоу или отмене

---

## 🚀 Быстрый Старт

1. Скопируйте нужные файлы-шаблоны
2. Замените `Example*` на ваши названия
3. Реализуйте логику работы с БД/API
4. Добавьте свои состояния и callback фабрики
5. Зарегистрируйте роутер в main.py

```python
# main.py
from bots.tg_bot import tg_bot_router

dp.include_router(tg_bot_router)
```
