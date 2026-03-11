# Примеры Использования Паттернов

## 1. Создание Простого Каталога с Пагинацией

### Шаг 1: Определите CallbackData

```python
# callback_datas.py
from aiogram.filters.callback_data import CallbackData

class ProductCallback(CallbackData, prefix="prod"):
    action: str  # "view", "select", "buy"
    product_id: int | None = None
    page: int | None = None
    category_id: int | None = None
```

### Шаг 2: Создайте Клавиатуру

```python
# keyboards/inline_kb.py
async def create_products_keyboard(
    products: list[dict],
    category_id: int,
    page: int = 0
):
    builder = InlineKeyboardBuilder()
    
    # Пагинация
    total_pages = math.ceil(len(products) / 10)
    start = page * 10
    end = start + 10
    
    # Кнопки товаров
    for product in products[start:end]:
        builder.button(
            text=f"{product['name']} - {product['price']}₽",
            callback_data=ProductCallback(
                action="select",
                product_id=product['id'],
                category_id=category_id
            )
        )
    builder.adjust(1)
    
    # Навигация
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=ProductCallback(
                        action="view",
                        page=page - 1,
                        category_id=category_id
                    ).pack()
                )
            )
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="noop"
            )
        )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=ProductCallback(
                        action="view",
                        page=page + 1,
                        category_id=category_id
                    ).pack()
                )
            )
        builder.row(*nav_buttons)
    
    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К категориям",
            callback_data=ProductCallback(action="back_to_categories").pack()
        )
    )
    
    return builder.as_markup()
```

### Шаг 3: Обработчики

```python
# handlers/callbacks.py
@router.callback_query(ProductCallback.filter(F.action == "view"))
async def show_products_page(
    call: CallbackQuery,
    callback_data: ProductCallback,
    session: AsyncSession
):
    await call.answer()
    
    products = await get_products_by_category(
        session,
        callback_data.category_id
    )
    
    keyboard = await create_products_keyboard(
        products=products,
        category_id=callback_data.category_id,
        page=callback_data.page
    )
    
    await call.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(ProductCallback.filter(F.action == "select"))
async def show_product_details(
    call: CallbackQuery,
    callback_data: ProductCallback,
    session: AsyncSession
):
    await call.answer()
    
    product = await get_product_by_id(session, callback_data.product_id)
    
    text = (
        f"📦 <b>{product['name']}</b>\n\n"
        f"💰 Цена: {product['price']}₽\n"
        f"📝 Описание: {product['description']}\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🛒 Купить",
        callback_data=ProductCallback(
            action="buy",
            product_id=product['id']
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к списку",
            callback_data=ProductCallback(
                action="view",
                category_id=callback_data.category_id,
                page=0
            ).pack()
        )
    )
    
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
```

---

## 2. Форма Регистрации с FSM

### Шаг 1: Определите Состояния

```python
# states.py
class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_email = State()
    waiting_for_confirmation = State()
```

### Шаг 2: Команда Старта

```python
# handlers/commands.py
@router.message(Command("register"))
async def start_registration(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_name)
    
    await message.answer(
        "👤 <b>Регистрация</b>\n\n"
        "Введите ваше имя:",
        parse_mode="HTML"
    )
```

### Шаг 3: Обработчики Состояний

```python
# handlers/messages.py
@router.message(StateFilter(RegistrationStates.waiting_for_name), F.text)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    
    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Попробуйте еще раз:")
        return
    
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_for_phone)
    
    # Клавиатура для отправки контакта
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📱 Отправить контакт", request_contact=True)
    )
    
    await message.answer(
        f"✅ Отлично, {name}!\n\n"
        "Теперь отправьте ваш номер телефона:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


@router.message(StateFilter(RegistrationStates.waiting_for_phone), F.contact)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    
    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.waiting_for_email)
    
    await message.answer(
        "✅ Номер телефона сохранен!\n\n"
        "Введите ваш email:",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(StateFilter(RegistrationStates.waiting_for_email), F.text)
async def process_email(message: Message, state: FSMContext):
    email = message.text.strip()
    
    # Валидация email
    if not validate_email(email):
        await message.answer("❌ Некорректный email. Попробуйте еще раз:")
        return
    
    await state.update_data(email=email)
    
    # Получаем все данные
    data = await state.get_data()
    
    # Показываем подтверждение
    text = (
        "📋 <b>Проверьте данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"📧 Email: {email}\n\n"
        "Все верно?"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data="confirm_registration"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel_registration")
    )
    
    await state.set_state(RegistrationStates.waiting_for_confirmation)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "confirm_registration")
async def confirm_registration(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    await call.answer()
    
    data = await state.get_data()
    
    # Сохраняем в БД
    await save_user_to_db(session, call.from_user.id, data)
    
    await state.clear()
    
    await call.message.edit_text(
        "🎉 <b>Регистрация завершена!</b>\n\n"
        "Добро пожаловать!",
        parse_mode="HTML",
        reply_markup=None
    )
```

---

## 3. Загрузка и Обработка Файлов

### Обработчик Загрузки Документа

```python
# handlers/messages.py
@router.message(StateFilter(FormStates.waiting_for_file), F.document)
async def process_document(message: Message, state: FSMContext, bot: Bot):
    document = message.document
    
    # Проверка типа файла
    allowed_types = ['.pdf', '.doc', '.docx']
    if not any(document.file_name.endswith(ext) for ext in allowed_types):
        await message.answer(
            "❌ Неподдерживаемый формат файла.\n"
            "Разрешены: PDF, DOC, DOCX"
        )
        return
    
    # Проверка размера
    max_size = 10 * 1024 * 1024  # 10 МБ
    if document.file_size > max_size:
        await message.answer("❌ Файл слишком большой (макс. 10 МБ)")
        return
    
    # Скачивание файла
    file = await bot.get_file(document.file_id)
    file_bytes = await bot.download_file(file.file_path)
    
    # Сохранение или обработка
    await state.update_data(
        file_id=document.file_id,
        file_name=document.file_name,
        file_bytes=file_bytes.read()
    )
    
    await message.answer(
        f"✅ Файл '{document.file_name}' загружен!\n\n"
        "Что делать дальше?"
    )
```

### Обработчик Фото

```python
@router.message(F.photo)
async def process_photo(message: Message, bot: Bot):
    # Берем фото в лучшем качестве
    photo = message.photo[-1]
    
    # Скачиваем
    file = await bot.get_file(photo.file_id)
    photo_bytes = await bot.download_file(file.file_path)
    
    # Обработка (например, распознавание текста, сжатие и т.д.)
    # ...
    
    await message.answer("✅ Фото обработано!")
```

---

## 4. Работа с Медиагруппами

### Отправка Нескольких Файлов

```python
from aiogram.types import InputMediaDocument, BufferedInputFile

async def send_multiple_files(message: Message, files_data: list[dict]):
    """
    files_data = [
        {"bytes": b"...", "filename": "file1.pdf"},
        {"bytes": b"...", "filename": "file2.pdf"},
    ]
    """
    media_group = []
    
    for i, file_data in enumerate(files_data):
        file_to_send = BufferedInputFile(
            file_data['bytes'],
            filename=file_data['filename']
        )
        media_group.append(InputMediaDocument(media=file_to_send))
    
    # Подпись только у первого
    media_group[0].caption = (
        f"📦 Ваши файлы готовы!\n\n"
        f"Всего файлов: {len(files_data)}"
    )
    media_group[0].parse_mode = "HTML"
    
    await message.answer_media_group(media=media_group)
```

---

## 5. Анимация Загрузки

### Простая Анимация

```python
async def show_loading_animation(message: Message, duration: float = 3.0):
    """Показывает анимацию загрузки."""
    frames = ["⏳", "⌛️"]
    
    start_time = asyncio.get_event_loop().time()
    i = 0
    
    while asyncio.get_event_loop().time() - start_time < duration:
        try:
            await message.edit_text(f"{frames[i % len(frames)]} Загрузка...")
            await asyncio.sleep(0.5)
            i += 1
        except TelegramBadRequest:
            break

# Использование
@router.message(Command("process"))
async def process_command(message: Message):
    loading_msg = await message.answer("⏳ Загрузка...")
    
    # Запускаем анимацию
    animation_task = asyncio.create_task(
        show_loading_animation(loading_msg, duration=5.0)
    )
    
    try:
        # Долгая операция
        result = await long_operation()
    finally:
        animation_task.cancel()
    
    await loading_msg.edit_text(f"✅ Готово! Результат: {result}")
```

### Прогресс-бар

```python
async def animate_progress_bar(message: Message, base_text: str):
    """Анимирует прогресс-бар."""
    frames = [
        "▱▱▱▱▱▱",
        "▰▱▱▱▱▱",
        "▰▰▱▱▱▱",
        "▰▰▰▱▱▱",
        "▰▰▰▰▱▱",
        "▰▰▰▰▰▱",
        "▰▰▰▰▰▰",
    ]
    
    while True:
        for frame in frames:
            try:
                await message.edit_text(f"{base_text}\n\n{frame}")
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                return
            except TelegramBadRequest:
                return
```

---

## 6. Работа с Базой Данных

### Паттерн Repository

```python
# services/database.py
class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_or_create(self, telegram_id: int, user_data: dict):
        """Получает или создает пользователя."""
        user = await self.session.get(User, telegram_id)
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=user_data.get('username'),
                full_name=user_data.get('full_name')
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        
        return user
    
    async def update_balance(self, telegram_id: int, amount: int):
        """Обновляет баланс пользователя."""
        user = await self.session.get(User, telegram_id)
        if user:
            user.balance += amount
            await self.session.commit()
            return user
        return None

# Использование в handlers
@router.message(Command("balance"))
async def show_balance(message: Message, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get_or_create(
        message.from_user.id,
        {
            'username': message.from_user.username,
            'full_name': message.from_user.full_name
        }
    )
    
    await message.answer(f"💰 Ваш баланс: {user.balance}₽")
```

---

## 7. Middleware для Логирования

```python
# middlewares/logging_middleware.py
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user
        logger.info(
            f"User {user.id} (@{user.username}): {event.text or '[media]'}"
        )
        
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await event.answer("❌ Произошла ошибка. Попробуйте позже.")
```

---

## 8. Админ-панель

```python
# handlers/admin.py
from bots.tg_bot.filters.is_admin import IsAdminFilter

admin_router = Router(name="admin")
admin_router.message.filter(IsAdminFilter())

@admin_router.message(Command("stats"))
async def show_stats(message: Message, session: AsyncSession):
    """Показывает статистику (только для админов)."""
    total_users = await get_total_users(session)
    active_today = await get_active_users_today(session)
    
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Активных сегодня: {active_today}"
    )
    
    await message.answer(text, parse_mode="HTML")


@admin_router.message(Command("broadcast"))
async def start_broadcast(message: Message, state: FSMContext):
    """Начинает рассылку."""
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await message.answer("Введите текст для рассылки:")


@admin_router.message(StateFilter(AdminStates.waiting_for_broadcast_text))
async def process_broadcast(message: Message, state: FSMContext, session: AsyncSession):
    """Отправляет рассылку всем пользователям."""
    text = message.text
    users = await get_all_users(session)
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await message.bot.send_message(user.telegram_id, text)
            success += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except Exception:
            failed += 1
    
    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена!\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}"
    )
```

Эти примеры покрывают большинство типичных сценариев разработки Telegram ботов!
