"""
Callback Query Handlers

Паттерн: Обработка callback запросов от inline кнопок
- Используйте CallbackData фабрики с фильтрами
- Всегда вызывайте call.answer() для снятия "часиков"
- Используйте call.message.edit_* для обновления сообщений
- Обрабатывайте ошибки (сообщение может быть удалено)
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bots.tg_bot.callback_datas import ExampleItemCallback, ExampleNavigationCallback
from bots.tg_bot.keyboards.inline_kb import create_paginated_keyboard

logger = logging.getLogger(__name__)

router = Router(name="callbacks")


@router.callback_query(ExampleItemCallback.filter(F.action == "view"))
async def process_pagination(call: CallbackQuery, callback_data: ExampleItemCallback):
    """
    Обработчик пагинации списка.

    Паттерн:
    - Фильтр по action
    - Немедленный ответ на callback
    - Обновление только клавиатуры (без изменения текста)
    """
    await call.answer()

    page = callback_data.page or 0

    # Здесь должна быть логика получения данных
    # items = await get_items_from_db()
    items = [{"id": i, "name": f"Элемент {i}"} for i in range(1, 51)]

    keyboard = await create_paginated_keyboard(items=items, page=page, callback_factory=ExampleItemCallback)

    try:
        await call.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest as e:
        logger.warning(f"Failed to edit message: {e}")
        await call.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)


@router.callback_query(ExampleItemCallback.filter(F.action == "select"))
async def process_item_selection(call: CallbackQuery, callback_data: ExampleItemCallback):
    """
    Обработчик выбора элемента из списка.

    Паттерн:
    - Получение данных по ID
    - Обновление текста и клавиатуры
    - Переход к следующему шагу
    """
    await call.answer()

    item_id = callback_data.item_id

    # Здесь должна быть логика получения данных
    # item = await get_item_by_id(item_id)

    text = f"✅ Вы выбрали элемент #{item_id}\n\nЧто хотите сделать дальше?"

    try:
        await call.message.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        await call.message.answer(text, parse_mode="HTML")


@router.callback_query(ExampleItemCallback.filter(F.action == "cancel"))
async def process_cancel(call: CallbackQuery, state: FSMContext):
    """
    Обработчик отмены действия.

    Паттерн:
    - Очистка состояния
    - Удаление клавиатуры
    - Информирование пользователя
    """
    await call.answer()
    await state.clear()

    try:
        await call.message.edit_text("❌ Действие отменено.\nИспользуйте /start для начала работы.", reply_markup=None)
    except TelegramBadRequest:
        await call.message.answer("❌ Действие отменено.")


@router.callback_query(ExampleNavigationCallback.filter(F.action == "back"))
async def process_back_navigation(call: CallbackQuery, callback_data: ExampleNavigationCallback):
    """
    Обработчик кнопки "Назад".

    Паттерн:
    - Контекстный возврат (from_section)
    - Восстановление предыдущего меню
    """
    await call.answer()

    from_section = callback_data.from_section

    text = f"⬅️ Возвращаемся из раздела: {from_section}"

    try:
        await call.message.edit_text(text)
    except TelegramBadRequest:
        await call.message.answer(text)


@router.callback_query(F.data == "noop")
async def process_noop(call: CallbackQuery):
    """
    Обработчик для "пустых" кнопок (например, индикатор страницы).

    Паттерн:
    - Просто отвечаем на callback без действий
    - Можно показать alert с информацией
    """
    await call.answer("Это индикатор страницы", show_alert=False)
