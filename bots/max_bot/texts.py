"""
Static texts for MAX Bot AITAT-Dispatcher.
All messages that the bot sends to users.

This file contains MAX-specific messages. For messages shared with Telegram bot,
import from bots.tg_bot.texts where applicable.
"""

# Import shared texts from Telegram bot
from bots.tg_bot.texts import (
    # Registration messages
    REGISTRATION_START,
    REGISTRATION_PHONE_SHARED,
    REGISTRATION_ENTER_EMAIL,
    REGISTRATION_ENTER_INN,
    REGISTRATION_ENTER_KEY,
    REGISTRATION_KEY_HELP,
    REGISTRATION_PROCESSING,
    REGISTRATION_SUBMITTED,
    REGISTRATION_SUCCESS,
    REGISTRATION_REJECTED,
    REGISTRATION_PENDING,
    REGISTRATION_KEY_CONFLICT,
    REGISTRATION_PHONE_DUPLICATE,
    REGISTRATION_INVALID_INN,
    
    # Main menu
    MAIN_MENU,
    
    # Profile messages
    PROFILE_INFO,
    PROFILE_ORGANIZATIONS_LIST,
    PROFILE_KEYS_LIST,
    PROFILE_NO_SUBSCRIPTION,
    PROFILE_ACTIVE_SUBSCRIPTION,
    PROFILE_EXPIRED_SUBSCRIPTION,
    PROFILE_NOTIFICATIONS_ON,
    PROFILE_NOTIFICATIONS_OFF,
    PROFILE_ADD_INN_PROMPT,
    PROFILE_INN_ADDED,
    PROFILE_INN_DUPLICATE,
    PROFILE_ADD_KEY_PROMPT,
    ADD_KEY_SUCCESS,
    ADD_KEY_CONFLICT,
    PROFILE_CHANGE_PHONE_PROMPT,
    PROFILE_CHANGE_PHONE_SUBMITTED,
    PROFILE_PHONE_CHANGE_PROMPT,
    PROFILE_PHONE_CHANGE_CONFIRM,
    PROFILE_PHONE_CHANGE_SUBMITTED,
    PROFILE_NOTIFICATIONS_TOGGLED,
    PROFILE_NOTIFICATIONS_ENABLED_DESC,
    PROFILE_NOTIFICATIONS_DISABLED_DESC,
    PROFILE_NOTIFICATIONS_DISABLE_CONFIRM,
    PROFILE_NOTIFICATIONS_DISABLED_SUCCESS,
    PROFILE_NOTIFICATIONS_ENABLED_SUCCESS,
    ERROR_VALIDATION_EMAIL,
    
    # Invoice messages
    INVOICE_SELECT_ORGANIZATION,
    INVOICE_ADD_NEW_INN,
    INVOICE_INN_ADDED,
    INVOICE_INN_DUPLICATE,
    INVOICE_SELECT_KEYS,
    INVOICE_ADD_NEW_KEY,
    INVOICE_KEY_ADDED,
    INVOICE_DESCRIPTION_REMINDER,
    INVOICE_KEY_CONFLICT,
    INVOICE_ENTER_DESCRIPTION,
    INVOICE_SELECT_DELIVERY,
    INVOICE_CONFIRM_EMAIL,
    INVOICE_ENTER_EMAIL,
    INVOICE_CONFIRMATION,
    INVOICE_PROCESSING,
    INVOICE_CREATED,
    INVOICE_CREATED_NO_MANAGER,
    INVOICE_RESPONSE_TIME_WORKING,
    INVOICE_RESPONSE_TIME_EXTENDED,
    INVOICE_RESPONSE_TIME_NON_WORKING,
    INVOICE_READY,
    INVOICE_SENT_TO_EMAIL,
    
    # Support messages
    SUPPORT_CREATE_TICKET,
    SUPPORT_SELECT_ORGANIZATION,
    SUPPORT_SELECT_KEY_CONTEXT,
    SUPPORT_TICKET_CREATED,
    SUPPORT_ROUTING_REGULAR,
    SUPPORT_ROUTING_EXTENDED,
    SUPPORT_ROUTING_NON_WORKING,
    SUPPORT_RESPONSE_TIME_REGULAR,
    SUPPORT_RESPONSE_TIME_EXTENDED,
    SUPPORT_RESPONSE_TIME_NON_WORKING,
    SUPPORT_TICKET_ASSIGNED,
    SUPPORT_TICKET_CLOSED,
    SUPPORT_TICKET_CANCELLED,
    
    # Renewal messages
    RENEWAL_STATUS_ACTIVE,
    RENEWAL_STATUS_ACTIVE_NO_DATE,
    RENEWAL_STATUS_EXPIRED,
    RENEWAL_STATUS_NONE,
    RENEWAL_TICKET_CREATED,
    RENEWAL_ERROR_NO_MANAGER,
    RENEWAL_ERROR_CREATE_TICKET,
    RENEWAL_REMINDER_30_DAYS,
    RENEWAL_REMINDER_7_DAYS,
    SUPPORT_SUBSCRIPTION_EXPIRED,
    SUPPORT_NO_SUBSCRIPTION,
    
    # Error messages
    ERROR_GENERAL,
    ERROR_NO_ACCESS,
    ERROR_INVALID_INPUT,
    ERROR_TIMEOUT,
    ERROR_API_UNAVAILABLE,
    ERROR_VALIDATION_PHONE,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_EMAIL,
    ERROR_TEXT_TOO_LONG,
    
    # Flow control
    FLOW_CANCELLED,
    FLOW_CANCEL_PROMPT,
    
    # Help
    HELP_TEXT,
    
    # Main Menu Buttons
    MENU_PROFILE,
    MENU_INVOICE,
    MENU_SUPPORT,
    MENU_RENEWAL,
    MENU_RATE_SERVICE,
    MENU_ARCHIVE,
    
    # Buttons
    BTN_BACK,
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_SKIP,
    BTN_RETRY,
    BTN_CONTACT_SUPPORT,
    BTN_MAIN_MENU,
    BTN_SHARE_PHONE,
    BTN_ADD_NEW_INN,
    BTN_ADD_ANOTHER_KEY,
    BTN_DONE,
    BTN_DONT_KNOW,
    BTN_DELIVERY_TELEGRAM,
    BTN_DELIVERY_EMAIL,
    BTN_ADD_INN,
    BTN_ADD_KEY,
    BTN_CHANGE_PHONE,
    BTN_TOGGLE_NOTIFICATIONS,
    BTN_ENTER_ANOTHER_KEY,
    BTN_CONTINUE_REGISTRATION,
    BTN_CREATE_RENEWAL_REQUEST,
    BTN_CONTACT_MANAGER,
)


# ========== MAX-Specific Messages ==========

MENU_INVOICE = "Менеджер"
MENU_RENEWAL = "🔄 Активация подписки"

# These messages are specific to MAX messenger and differ from Telegram

# Registration: Organization name request when INN not found in 1C
REGISTRATION_ENTER_ORG_NAME = """
ℹ️ <b>ИНН не найден в базе 1С</b>

ИНН <code>{inn}</code> не найден в нашей базе данных.

Вы можете ввести <b>короткое название организации</b> (для удобства отображения в боте) или пропустить этот шаг.

<i>Название будет использоваться только в интерфейсе бота.</i>
"""

# Generic org name request (used in invoice, consultation, profile flows)
ENTER_ORG_NAME = """
ℹ️ <b>ИНН не найден в базе 1С</b>

ИНН <code>{inn}</code> не найден в нашей базе данных.

Вы можете ввести <b>короткое название организации</b> (для удобства отображения в боте) или пропустить этот шаг.

<i>Название будет использоваться только в интерфейсе бота.</i>
"""

MAX_WELCOME = """
👋 Привет! Рады видеть вас в MAX боте АЙТАТ!

Я ваш персональный помощник для работы с ГРАНД-Сметой. Помогу получить счета, решить технические вопросы и продлить подписку.

Нажмите /start, чтобы начать! 🚀
"""

# Main menu text with correct terminology
# ГРАНД-Смета - это программа
# Ключ ГРАНД-Сметы - это лицензионный ключ
# Подписка на ИТС - это платная техподдержка
MAX_MAIN_MENU_TEXT = """
🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>

Здесь вы можете:

<b>Менеджер</b>
Получить помощь от менеджера

🆘 <b>Техподдержка</b>
Получить помощь по работе с программой ГРАНД-Смета

💬 <b>Сметная консультация</b>
Задать вопрос сметному специалисту

🗃️ <b>Архив</b>
Посмотреть историю ваших обращений

👤 <b>Мой профиль</b>
Управление данными и настройками

Выберите нужное действие 👇
"""

# ========== Employee Interface ==========

EMPLOYEE_MENU_TEXT = """
👨‍💼 <b>Меню сотрудника</b>

Добро пожаловать! Выберите действие 👇
"""

EMPLOYEE_NO_ACTIVE_TICKETS_TEXT = """
📥 <b>Активные заявки</b>

Пока нет активных заявок — можно выдохнуть! 😊

Как только появятся новые обращения, они отобразятся здесь.
"""

EMPLOYEE_SETTINGS_TEXT = """
⚙️ <b>Настройки сотрудника</b>

<b>ФИО:</b> {full_name}
<b>Должность:</b> {position}
<b>Роль:</b> {role}

<b>Подпись:</b> {signature}
"""


# ========== Employee Interface Buttons ==========

BTN_ACTIVE_TICKETS = "📥 Активные заявки"
BTN_ARCHIVE_SEARCH = "🗃️ Архив обращений"
BTN_EMPLOYEE_SETTINGS = "⚙️ Настройки"
BTN_ADMIN_PANEL = "🔐 Админ-панель"


# ========== Admin Panel Messages ==========

ADMIN_PANEL_MENU = """🔐 <b>Административная панель</b>

Выберите раздел для управления:

👥 <b>Сотрудники</b> - управление персоналом
📋 <b>Операции</b> - регистрации, рассылки, конфликты, смена номера
📅 <b>График работы</b> - настройка расписания
⚙️ <b>Настройки</b> - системные параметры
📊 <b>Статистика</b> - аналитика и отчеты"""


# ========== Registration Messages ==========

REGISTRATION_APPROVED = """
🎉 <b>Отличные новости!</b>

Ваша регистрация одобрена — добро пожаловать в систему! 

<b>Теперь вам доступно:</b>
💰 Получение счетов на оплату
🆘 Быстрая техническая поддержка  
🔄 Активация подписки в пару кликов

Нажмите /start, чтобы начать работу 🚀
"""

REGISTRATION_REJECTED = """
😔 <b>Регистрация отклонена</b>

К сожалению, мы не смогли одобрить вашу регистрацию.

<b>Причина:</b> {reason}

Если у вас есть вопросы или вы считаете, что произошла ошибка, свяжитесь с нами:
📞 +7 (8552) 25-33-33
"""


# MAX-specific profile messages
PROFILE_CHANGE_EMAIL_PROMPT = """
📧 <b>Изменение Email</b>

Введите новый email адрес:

<i>Email будет обновлен сразу после ввода.</i>
"""

PROFILE_EMAIL_UPDATED = """
✅ <b>Email успешно обновлен</b>

Новый email: <b>{email}</b>
"""

PROFILE_EMAIL_REMOVED = """
✅ <b>Email удален из профиля</b>
"""


# ============================================================================
# Admin Creation Messages
# ============================================================================

ADMIN_CREATION_START = """
🔐 <b>Создание администратора</b>

Для создания нового администратора системы необходимо:
1. Номер телефона
2. Полное имя (ФИО)

Пожалуйста, поделитесь номером телефона нового администратора.
"""

ADMIN_CREATION_ENTER_PHONE = """
📱 Пожалуйста, поделитесь номером телефона нового администратора.
"""

ADMIN_CREATION_INVALID_PHONE = """
❌ <b>Неверный формат номера телефона</b>

Пожалуйста, используйте кнопку "Поделиться номером" для отправки контакта.
"""

ADMIN_CREATION_ENTER_FULL_NAME = """
📝 <b>Введите полное имя администратора</b>

Формат: Фамилия Имя Отчество
Пример: Иванов Иван Иванович

Минимум: Фамилия и Имя
"""

ADMIN_CREATION_SUCCESS = """
✅ <b>Администратор успешно создан!</b>

👤 <b>ФИО:</b> {full_name}
📱 <b>Телефон:</b> {phone}
🆔 <b>User ID:</b> {user_id}
👔 <b>Staff ID:</b> {staff_id}

Администратор может войти в систему, используя команду /manager.
"""

ADMIN_CREATION_CANCELLED = """
❌ Создание администратора отменено.
"""


# ========== Non-Working Hours Messages ==========

# Friendly messages for tickets created outside working hours
# Requirements: Show friendly message with emoji and working hours info

def _get_time_greeting() -> str:
    """Return greeting and emoji based on current Moscow time (hour)."""
    from datetime import datetime, timezone, timedelta
    moscow_tz = timezone(timedelta(hours=3))
    hour = datetime.now(moscow_tz).hour
    if 5 <= hour < 12:
        return "☀️", "Доброе утро!"
    elif 12 <= hour < 18:
        return "🌤️", "Добрый день!"
    else:
        return "🌙", "Добрый вечер!"


def _ticket_number_line(ticket_id: int | None) -> str:
    return f"\n📋 <b>Номер заявки:</b> #{ticket_id}\n" if ticket_id is not None else ""


def get_invoice_non_working_hours_message(ticket_id: int | None = None) -> str:
    """Non-working hours message for invoice tickets with time-based greeting."""
    emoji, greeting = _get_time_greeting()
    return f"""
{emoji} <b>{greeting}</b> 
{_ticket_number_line(ticket_id)}

Ваша заявка поставлена в очередь. На данный момент нет свободных специалистов.

📅 <b>График работы специалистов:</b> Пн-Пт: 08:00-17:00, Cуб: 09:00-13:00

<i>График работы в праздничные дни может меняться.</i>

Ваш менеджер увидит заявку первым делом утром и свяжется с вами. Спасибо за понимание! 😊
"""


def get_support_non_working_hours_message(ticket_id: int | None = None) -> str:
    """Non-working hours message for support tickets with time-based greeting."""
    emoji, greeting = _get_time_greeting()
    return f"""
{emoji} <b>{greeting}</b> 
{_ticket_number_line(ticket_id)}

Ваша заявка поставлена в очередь. На данный момент нет свободных специалистов.

📅 <b>График работы специалистов:</b> Пн-Пт: 08:00-17:00, Cуб: 09:00-13:00

<i>График работы в праздничные дни может меняться.</i>

Мы ответим вам в начале рабочего дня. Спасибо за понимание! 😊
"""


def get_renewal_non_working_hours_message() -> str:
    """Non-working hours message for renewal tickets with time-based greeting."""
    emoji, greeting = _get_time_greeting()
    return f"""
{emoji} <b>{greeting}</b> 

Ваша заявка поставлена в очередь. На данный момент нет свободных специалистов.

📅 <b>График работы специалистов:</b> Пн-Пт: 08:00-17:00, Cуб: 09:00-13:00

<i>График работы в праздничные дни может меняться.</i>

Ваш менеджер свяжется с вами в начале рабочего дня. Спасибо за понимание! 😊
"""


# ========== Consultation Flow Messages ==========

CONSULTATION_SELECT_ORGANIZATION = """
🏢 <b>Консультация — Шаг 1 из 3</b>

Выберите организацию, по которой у вас возник вопрос, или пропустите этот шаг.
"""

CONSULTATION_ADD_NEW_INN = """
🏢 <b>Добавление организации</b>

Введите ИНН вашей организации (10 или 12 цифр):
"""

CONSULTATION_INN_ADDED = """
✅ <b>Организация добавлена!</b>

Теперь выберите её из списка для продолжения.
"""

CONSULTATION_INN_DUPLICATE = """
⚠️ Эта организация уже добавлена в ваш профиль.
"""

CONSULTATION_SELECT_KEYS = """
🔑 <b>Консультация — Шаг 2 из 3</b>

Выберите ключ(и) ГРАНД-Сметы, по которым у вас вопрос, или пропустите этот шаг.
"""

CONSULTATION_ADD_NEW_KEY = """
🔑 <b>Добавление ключа</b>

Введите номер ключа ГРАНД-Сметы:
"""

CONSULTATION_KEY_ADDED = """
✅ <b>Ключ добавлен!</b>

Теперь выберите его из списка для продолжения.
"""

CONSULTATION_ENTER_DESCRIPTION = """
💬 <b>Консультация — Шаг 3 из 3</b>

Опишите ваш вопрос подробно. Чем точнее описание — тем быстрее специалист сможет помочь.
"""

CONSULTATION_TICKET_CREATED = """
✅ <b>Заявка на консультацию создана!</b>

📋 <b>Номер заявки:</b> #{ticket_id}

Ваш вопрос передан сметному специалисту. Он свяжется с вами в ближайшее время.
"""

def get_consultation_non_working_hours_message(ticket_id: int | None = None) -> str:
    """Non-working hours message for consultation tickets with time-based greeting."""
    emoji, greeting = _get_time_greeting()
    return f"""
{emoji} <b>{greeting}</b>

✅ <b>Заявка на консультацию создана!</b>
{_ticket_number_line(ticket_id)}

Ваш вопрос поставлен в очередь.

📅 <b>График работы специалистов:</b> Пн-Пт: 08:00-17:00, Cуб: 09:00-13:00

<i>График работы в праздничные дни может меняться.</i>

Специалист свяжется с вами в начале рабочего дня. Спасибо за понимание! 😊
"""


# Keep for backward compatibility (working hours variant — no greeting needed)
CONSULTATION_TICKET_CREATED_NON_WORKING = get_consultation_non_working_hours_message()

CONSULTATION_KEY_CONFLICT = """
⚠️ <b>Конфликт ключа</b>

Этот ключ уже зарегистрирован за другим пользователем. Попробуйте другой ключ или пропустите этот шаг.
"""

CONSULTATION_NO_SUBSCRIPTION = """
🔒 <b>Консультация недоступна</b>

Сметная консультация доступна только клиентам с активной подпиской на ИТС.

Для получения консультации необходимо оформить подписку. Заявка на подписку уже отправлена вашему менеджеру — он свяжется с вами в ближайшее время.
"""

CONSULTATION_SUBSCRIPTION_EXPIRED = """
🔒 <b>Консультация недоступна</b>

Ваша подписка на ИТС истекла. Сметная консультация доступна только при активной подписке.

Заявка на активацию подписки уже отправлена вашему менеджеру — он свяжется с вами в ближайшее время.
"""

CONSULTATION_RENEWAL_ALREADY_EXISTS_NO_SUBSCRIPTION = """
🔒 <b>Консультация недоступна</b>

Сметная консультация доступна только клиентам с активной подпиской на ИТС.

Ваша заявка на оформление подписки (#{ticket_id}) уже находится в работе у менеджера — ожидайте, он свяжется с вами в ближайшее время.
"""

CONSULTATION_RENEWAL_ALREADY_EXISTS_EXPIRED = """
🔒 <b>Консультация недоступна</b>

Ваша подписка на ИТС истекла. Сметная консультация доступна только при активной подписке.

Ваша заявка на активацию подписки (#{ticket_id}) уже находится в работе у менеджера — ожидайте, он свяжется с вами в ближайшее время.
"""

# ========== Main Menu Welcome Text (used across multiple handlers) ==========

# MAIN_MENU_WELCOME_TEXT =  """
# 🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>

# Здесь вы можете:

# <b>Менеджер</b> — получить помощь от менеджера
# 🆘 <b>Техподдержка</b> — получить помощь по работе с программой ГРАНД-Смета
# 💬 <b>Сметная консультация</b> — задать вопрос сметному специалисту
# 🗃️ <b>Архив</b> — посмотреть историю ваших обращений
# 👤 <b>Мой профиль</b> — управление данными и настройками

# Выберите нужное действие 👇
# """


MAIN_MENU_WELCOME_TEXT =  """
🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>

Здесь вы можете:

<b>Менеджер</b>
Получить помощь от менеджера

🆘 <b>Техподдержка</b>
Получить помощь по работе с программой ГРАНД-Смета

💬 <b>Сметная консультация</b>
Задать вопрос сметному специалисту

🗃️ <b>Архив</b>
Посмотреть историю ваших обращений

👤 <b>Мой профиль</b>
Управление данными и настройками

Выберите нужное действие 👇
"""


# ========== Off-Hours Message for Active Ticket Replies ==========

def get_off_hours_reply_message(ticket_type_value: str, work_mode_value: str) -> str:
    """
    Return notification text when client sends a message to an active ticket
    outside of working hours for that ticket type.

    Rules (per ТЗ sections 3, 6.1, 7.1):
    - INVOICE / RENEWAL: only REGULAR hours → manager available.
      In EXTENDED or NON_WORKING → show off-hours notice.
    - TECHNICAL_SUPPORT / CONSULTATION: REGULAR + EXTENDED → staff available.
      Only NON_WORKING → show off-hours notice.

    Args:
        ticket_type_value: TicketType enum value string
        work_mode_value: WorkMode enum value string ("regular", "extended", "non_working")

    Returns:
        Human-readable HTML-formatted message string.
    """
    emoji, greeting = _get_time_greeting()

    # Extended hours: duty engineer handles TP/Consultation, but not Invoice/Renewal
    if work_mode_value == "extended":
        return (
            f"{emoji} <b>{greeting}</b>\n\n"
            "🕐 Сейчас <b>продлённое рабочее время</b> (17:00–20:00 МСК).\n\n"
            "Менеджер по счетам и коммерческим вопросам работает в основное время "
            "<b>Пн–Пт 08:00–17:00 МСК</b>.\n\n"
            "✅ Ваше сообщение сохранено и будет передано специалисту в начале рабочего дня.\n\n"
            "<i>⚠️ В праздничные дни график работы может меняться.</i>"
        )

    # Non-working hours: nobody available
    return (
        f"{emoji} <b>{greeting}</b>\n\n"
        "🕐 Сейчас <b>нерабочее время</b>.\n\n"
        "📅 <b>Основной график работы:</b> Пн–Пт 08:00–17:00 МСК\n"
        "📅 <b>Продлённое время (дежурство ТП):</b> Пн–Пт 17:00–20:00, Сб 09:00–13:00\n\n"
        "✅ Ваше сообщение сохранено и будет передано специалисту в начале рабочего дня.\n\n"
        "<i>⚠️ В праздничные дни график работы может меняться.</i>"
    )
