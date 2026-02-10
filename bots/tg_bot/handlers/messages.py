"""
Message Handlers

Паттерн: Обработка текстовых сообщений и медиа
- Используйте F (Magic Filter) для фильтрации по типу контента
- Используйте StateFilter для обработки в конкретных состояниях
- Обрабатывайте ошибки gracefully
"""

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bots.tg_bot.states import FormStates, RegistrationStates

logger = logging.getLogger(__name__)

router = Router(name="messages")


@router.message(StateFilter(RegistrationStates.waiting_for_name), F.text)
async def process_name_input(message: Message, state: FSMContext):
    """
    Обработчик ввода имени в состоянии регистрации.

    Паттерн:
    - Проверка на StateFilter
    - Валидация входных данных
    - Сохранение в FSMContext
    - Переход к следующему состоянию
    """
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Попробуйте еще раз:")
        return

    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_for_email)

    await message.answer(f"✅ Отлично, {name}!\n\nТеперь введите ваш email:")


@router.message(StateFilter(FormStates.waiting_for_file), F.document)
async def process_document_upload(message: Message, state: FSMContext):
    """
    Обработчик загрузки документа.

    Паттерн:
    - Фильтр по типу контента (F.document)
    - Получение информации о файле
    - Сохранение file_id для дальнейшей работы
    """
    document = message.document

    # Проверка размера файла (например, макс 10 МБ)
    max_size = 10 * 1024 * 1024
    if document.file_size > max_size:
        await message.answer("❌ Файл слишком большой. Максимальный размер: 10 МБ")
        return

    await state.update_data(file_id=document.file_id, file_name=document.file_name)

    await message.answer(f"✅ Файл '{document.file_name}' получен!\n\nПодтвердите отправку?")
    await state.set_state(FormStates.waiting_for_confirmation)


@router.message(F.photo)
async def process_photo(message: Message):
    """
    Обработчик фотографий (без привязки к состоянию).

    Паттерн:
    - Получение фото в лучшем качестве ([-1])
    - Сохранение file_id
    """
    photo = message.photo[-1]  # Берем фото в лучшем качестве

    await message.answer(
        f"📸 Фото получено!\nРазмер: {photo.file_size} байт\nID: <code>{photo.file_id}</code>", parse_mode="HTML"
    )


@router.message(F.text)
async def echo_handler(message: Message):
    """
    Эхо-обработчик для необработанных текстовых сообщений.

    Паттерн:
    - Ловит все текстовые сообщения, не обработанные выше
    - Полезен для отладки и fallback
    """
    await message.answer(f"Вы написали: {message.text}\n\nИспользуйте /help для списка команд.")
