"""
Escalation Notification Templates

Централизованный модуль шаблонов уведомлений для системы эскалации заявок.
Включает форматирование текстов, клавиатур и вспомогательные функции.

Requirements: 1.2, 1.3, 3.3
"""

from datetime import datetime
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Ticket, Staff_Member, TicketType, TicketStatus
from bots.tg_bot.callback_datas import EscalationCallback


# ========== Helper Functions ==========


def format_ticket_type(ticket_type: TicketType) -> str:
    """
    Форматирует тип заявки для отображения пользователю.
    
    Args:
        ticket_type: Тип заявки из enum TicketType
    
    Returns:
        Читаемое название типа заявки на русском языке
    
    Examples:
        >>> format_ticket_type(TicketType.INVOICE)
        'Счет'
        >>> format_ticket_type(TicketType.TECHNICAL_SUPPORT)
        'Техподдержка'
    """
    ticket_type_display = {
        TicketType.INVOICE: "Счет",
        TicketType.TECHNICAL_SUPPORT: "Техподдержка",
        TicketType.RENEWAL: "Продление"
    }
    return ticket_type_display.get(ticket_type, ticket_type.value)


def format_ticket_status(ticket_status: TicketStatus) -> str:
    """
    Форматирует статус заявки для отображения пользователю.
    
    Args:
        ticket_status: Статус заявки из enum TicketStatus
    
    Returns:
        Читаемое название статуса на русском языке
    
    Examples:
        >>> format_ticket_status(TicketStatus.NEW)
        'Новая'
        >>> format_ticket_status(TicketStatus.IN_PROGRESS)
        'В работе'
    """
    status_display = {
        TicketStatus.NEW: "Новая",
        TicketStatus.IN_PROGRESS: "В работе",
        TicketStatus.WAITING_CLIENT: "Ожидание клиента",
        TicketStatus.CLOSED: "Закрыта"
    }
    return status_display.get(ticket_status, ticket_status.value)


def calculate_time_elapsed(created_at: datetime) -> int:
    """
    Вычисляет время, прошедшее с момента создания заявки в минутах.
    
    Args:
        created_at: Дата и время создания заявки (MSK, naive datetime)
    
    Returns:
        Количество минут, прошедших с момента создания (округленное вниз)
    
    Examples:
        >>> from datetime import timedelta
        >>> from utils.timezone_helpers import get_moscow_now_naive
        >>> created = get_moscow_now_naive() - timedelta(minutes=15, seconds=30)
        >>> calculate_time_elapsed(created)
        15
    
    Note:
        created_at должен быть в MSK (как хранится в БД после миграции).
        Используем get_moscow_now_naive() для корректного сравнения.
    """
    from utils.timezone_helpers import get_moscow_now_naive
    return int((get_moscow_now_naive() - created_at).total_seconds() / 60)


def format_datetime(dt: datetime) -> str:
    """
    Форматирует дату и время для отображения пользователю в MSK.
    
    Args:
        dt: Объект datetime в MSK (как хранится в БД после миграции на MSK)
    
    Returns:
        Строка в формате "ДД.ММ.ГГГГ ЧЧ:ММ" в часовом поясе MSK
    
    Examples:
        >>> dt_msk = datetime(2024, 1, 15, 14, 30)  # 14:30 MSK
        >>> format_datetime(dt_msk)
        '15.01.2024 14:30'  # 14:30 MSK (без изменений)
    
    Note:
        После миграции на MSK время в БД уже хранится в MSK timezone,
        поэтому не требуется конвертация.
    """
    # БД уже хранит время в MSK, просто форматируем
    return dt.strftime('%d.%m.%Y %H:%M')


# ========== Reminder Notification (10 min) ==========


def get_reminder_notification_text(ticket: Ticket, time_elapsed: int) -> str:
    """
    Генерирует текст напоминания сотруднику о необработанной заявке (10 минут).
    
    Напоминание отправляется ответственному сотруднику через 10 минут после
    создания заявки, если она все еще имеет статус NEW.
    
    Args:
        ticket: Объект заявки с загруженными relationships (user)
        time_elapsed: Количество минут, прошедших с создания заявки
    
    Returns:
        HTML-форматированный текст напоминания
    
    Requirements: FR-1.3.1
    
    Example:
        >>> ticket = Ticket(id=123, ticket_type=TicketType.INVOICE)
        >>> ticket.user = User(full_name="Иван Иванов")
        >>> text = get_reminder_notification_text(ticket, 10)
        >>> "Заявка <b>#123</b>" in text
        True
    """
    client_name = ticket.user.full_name if ticket.user else "Неизвестен"
    ticket_type_text = format_ticket_type(ticket.ticket_type)
    
    return (
        f"⏰ <b>НАПОМИНАНИЕ!</b>\n\n"
        f"Заявка <b>#{ticket.id}</b> висит {time_elapsed} минут.\n"
        f"Тип: {ticket_type_text}\n"
        f"Клиент: {client_name}\n\n"
        f"⚠️ Возьмите в работу, иначе заявка будет эскалирована руководству!"
    )


# ========== Escalation Notification (20 min) ==========


def get_escalation_notification_text(
    ticket: Ticket, 
    time_elapsed: int,
    escalation_timeout: int | None = None,
    has_backup_managers: bool = False
) -> str:
    """
    Генерирует текст уведомления администратору об эскалации заявки.
    
    Уведомление отправляется всем активным администраторам после истечения
    таймаута эскалации, если заявка все еще имеет статус NEW.
    
    Args:
        ticket: Объект заявки с загруженными relationships (user, assigned_staff)
        time_elapsed: Количество минут, прошедших с создания заявки
        escalation_timeout: Настроенный таймаут эскалации в минутах (из БД)
        has_backup_managers: Были ли настроены резервные менеджеры
    
    Returns:
        HTML-форматированный текст уведомления об эскалации
    
    Requirements: FR-1.3.2
    
    Example:
        >>> ticket = Ticket(id=123, ticket_type=TicketType.TECHNICAL_SUPPORT)
        >>> ticket.user = User(full_name="Петр Петров")
        >>> ticket.assigned_staff = Staff_Member(full_name="Сергей Сергеев")
        >>> ticket.created_at = datetime(2024, 1, 15, 14, 0)
        >>> text = get_escalation_notification_text(ticket, 20, 10, False)
        >>> "ЭСКАЛАЦИЯ" in text
        True
    """
    client_name = ticket.user.full_name if ticket.user else "Неизвестен"
    ticket_type_text = format_ticket_type(ticket.ticket_type)
    assigned_name = ticket.assigned_staff.full_name if ticket.assigned_staff else "Не назначен"
    created_time = format_datetime(ticket.created_at)
    
    # Формируем причину эскалации в зависимости от наличия резервных менеджеров
    if has_backup_managers:
        reason = (
            f"Заявка не была взята в работу в течение {escalation_timeout or 'установленного'} минут. "
            f"Основной менеджер и резервные менеджеры не ответили."
        )
    else:
        reason = (
            f"Заявка не была взята в работу в течение {escalation_timeout or 'установленного'} минут. "
            f"Назначенный менеджер не ответил. Резервные менеджеры не настроены."
        )
    
    # Подсказка об изменении таймаута
    timeout_hint = (
        f"\n💡 <i>Таймаут эскалации ({escalation_timeout or '?'} мин) можно изменить в "
        f"админ-панели → Настройки → Таймауты</i>"
    ) if escalation_timeout else ""
    
    return (
        f"🔥 <b>ЭСКАЛАЦИЯ!</b> Заявка <b>#{ticket.id}</b> висит {time_elapsed} мин!\n\n"
        f"📋 <b>Причина:</b> {reason}\n\n"
        f"Тип: {ticket_type_text}\n"
        f"Клиент: {client_name}\n"
        f"Ответственный: {assigned_name}\n"
        f"Создана: {created_time}\n"
        f"{timeout_hint}\n"
        f"⚠️ Требуется срочное вмешательство!"
    )


def get_escalation_notification_keyboard(
    escalation_id: int,
    ticket_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с быстрыми действиями для уведомления об эскалации.
    
    Клавиатура включает кнопки для переназначения, взятия на себя и
    контакта с ответственным сотрудником.
    
    Args:
        escalation_id: ID эскалации
        ticket_id: ID заявки
    
    Returns:
        InlineKeyboardMarkup с кнопками быстрых действий
    
    Requirements: FR-1.3.2
    
    Layout:
        [➡️ Переназначить]
        [🙋‍♂️ Взять на себя]
        [📞 Позвонить сотруднику]
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="➡️ Переназначить",
        callback_data=EscalationCallback(
            action="reassign",
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
    )
    
    builder.button(
        text="🙋‍♂️ Взять на себя",
        callback_data=EscalationCallback(
            action="take_over",
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
    )
    
    # builder.button(
    #     text="📞 Позвонить сотруднику",
    #     callback_data=EscalationCallback(
    #         action="contact",
    #         escalation_id=escalation_id,
    #         ticket_id=ticket_id
    #     )
    # )
    
    # One button per row
    builder.adjust(1)
    
    return builder.as_markup()


# ========== Reassignment Notifications ==========


def get_reassignment_notification_text(
    ticket: Ticket,
    new_staff: Staff_Member,
    admin_name: str
) -> str:
    """
    Генерирует текст уведомления новому сотруднику о переназначении заявки.
    
    Уведомление отправляется сотруднику, которому администратор переназначил
    заявку через интерфейс эскалации.
    
    Args:
        ticket: Объект заявки с загруженными relationships (user)
        new_staff: Объект нового ответственного сотрудника
        admin_name: ФИО администратора, выполнившего переназначение
    
    Returns:
        HTML-форматированный текст уведомления о переназначении
    
    Requirements: FR-1.6.3
    
    Example:
        >>> ticket = Ticket(id=123, ticket_type=TicketType.INVOICE)
        >>> ticket.user = User(full_name="Анна Смирнова")
        >>> staff = Staff_Member(full_name="Дмитрий Дмитриев")
        >>> text = get_reassignment_notification_text(ticket, staff, "Админ Админов")
        >>> "переназначена" in text
        True
    """
    client_name = ticket.user.full_name if ticket.user else "Неизвестен"
    ticket_type_text = format_ticket_type(ticket.ticket_type)
    
    return (
        f"➡️ <b>Заявка переназначена на вас</b>\n\n"
        f"Заявка <b>#{ticket.id}</b> была переназначена администратором {admin_name}.\n\n"
        f"Тип: {ticket_type_text}\n"
        f"Клиент: {client_name}\n"
        f"Статус: В работе\n\n"
        f"Пожалуйста, свяжитесь с клиентом как можно скорее."
    )


def get_reassignment_success_text(ticket_id: int, staff_name: str) -> str:
    """
    Генерирует текст подтверждения успешного переназначения для администратора.
    
    Args:
        ticket_id: ID переназначенной заявки
        staff_name: ФИО сотрудника, которому переназначена заявка
    
    Returns:
        HTML-форматированный текст подтверждения
    
    Requirements: FR-1.6.3
    
    Example:
        >>> text = get_reassignment_success_text(123, "Елена Еленова")
        >>> "успешно переназначена" in text
        True
    """
    return (
        f"✅ <b>Заявка успешно переназначена</b>\n\n"
        f"Заявка <b>#{ticket_id}</b> переназначена на {staff_name}.\n"
        f"Сотрудник получил уведомление.\n"
        f"Эскалация закрыта."
    )


# ========== Take Over Notifications ==========


def get_take_over_client_notification_text(
    ticket: Ticket,
    admin_signature: str
) -> str:
    """
    Генерирует текст уведомления клиенту о взятии заявки администратором.
    
    Уведомление отправляется клиенту, когда администратор берет заявку на себя
    через интерфейс эскалации.
    
    Args:
        ticket: Объект заявки
        admin_signature: Подпись администратора (ФИО и контакты)
    
    Returns:
        HTML-форматированный текст уведомления клиенту
    
    Requirements: FR-1.7.1
    
    Example:
        >>> ticket = Ticket(id=123, ticket_type=TicketType.RENEWAL)
        >>> signature = "Олег Олегов\\nТел: +7 (999) 123-45-67"
        >>> text = get_take_over_client_notification_text(ticket, signature)
        >>> "взята в работу" in text
        True
    """
    ticket_type_text = format_ticket_type(ticket.ticket_type)
    
    return (
        f"✅ <b>Ваша заявка взята в работу</b>\n\n"
        f"Заявка <b>#{ticket.id}</b> ({ticket_type_text}) взята в работу.\n\n"
        f"С вами работает:\n{admin_signature}"
    )


def get_take_over_success_text(ticket_id: int) -> str:
    """
    Генерирует текст подтверждения успешного взятия заявки для администратора.
    
    Args:
        ticket_id: ID взятой заявки
    
    Returns:
        HTML-форматированный текст подтверждения
    
    Requirements: FR-1.7.1
    
    Example:
        >>> text = get_take_over_success_text(123)
        >>> "взята на себя" in text
        True
    """
    return (
        f"✅ <b>Заявка взята на себя</b>\n\n"
        f"Заявка <b>#{ticket_id}</b> теперь назначена на вас.\n"
        f"Клиент получил уведомление.\n"
        f"Эскалация закрыта.\n\n"
        f"Теперь вы можете общаться с клиентом."
    )


# ========== Contact Staff Information ==========


def get_contact_staff_text(staff: Staff_Member) -> str:
    """
    Генерирует текст с контактной информацией сотрудника.
    
    Показывается администратору при выборе действия "Позвонить сотруднику"
    в интерфейсе эскалации.
    
    Args:
        staff: Объект сотрудника с контактной информацией
    
    Returns:
        HTML-форматированный текст с контактами
    
    Requirements: FR-1.8.1
    
    Example:
        >>> staff = Staff_Member(
        ...     full_name="Игорь Игорев",
        ...     staff_role=StaffRole.MANAGER,
        ...     tg_user_id=123456789,
        ...     phone_number="+79991234567",
        ...     email="igor@example.com"
        ... )
        >>> text = get_contact_staff_text(staff)
        >>> "Игорь Игорев" in text
        True
    """
    # Role display
    role_display = {
        "MANAGER": "Менеджер",
        "TECHNICAL_SUPPORT": "Техподдержка",
        "DUTY_ENGINEER": "Дежурный инженер",
        "ADMINISTRATOR": "Администратор"
    }
    role_text = role_display.get(staff.staff_role.value, staff.staff_role.value)
    
    # Build contact info
    contact_lines = [
        f"📞 <b>Контакты сотрудника</b>\n",
        f"ФИО: {staff.full_name}",
        f"Роль: {role_text}"
    ]
    
    if staff.tg_user_id:
        contact_lines.append(f"Telegram ID: <code>{staff.tg_user_id}</code>")
    
    if staff.phone_number:
        contact_lines.append(f"Телефон: {staff.phone_number}")
    
    if staff.email:
        contact_lines.append(f"Email: {staff.email}")
    
    return "\n".join(contact_lines)


# ========== Error Messages ==========


def get_error_escalation_not_found() -> str:
    """
    Генерирует текст ошибки, когда эскалация не найдена.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "❌ <b>Ошибка</b>\n\n"
        "Эскалация не найдена или уже разрешена."
    )


def get_error_escalation_already_resolved() -> str:
    """
    Генерирует текст ошибки, когда эскалация уже разрешена.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "⚠️ <b>Эскалация уже разрешена</b>\n\n"
        "Другой администратор уже обработал эту эскалацию."
    )


def get_error_no_staff_available() -> str:
    """
    Генерирует текст ошибки, когда нет доступных сотрудников для переназначения.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "❌ <b>Ошибка</b>\n\n"
        "Нет доступных сотрудников для переназначения."
    )


def get_error_staff_not_found() -> str:
    """
    Генерирует текст ошибки, когда сотрудник не найден.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "❌ <b>Ошибка</b>\n\n"
        "Сотрудник не найден или неактивен."
    )


def get_error_ticket_not_found() -> str:
    """
    Генерирует текст ошибки, когда заявка не найдена.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "❌ <b>Ошибка</b>\n\n"
        "Заявка не найдена."
    )


def get_error_generic() -> str:
    """
    Генерирует текст общей ошибки.
    
    Returns:
        Текст сообщения об ошибке
    """
    return (
        "❌ <b>Произошла ошибка</b>\n\n"
        "Пожалуйста, попробуйте позже или обратитесь к администратору."
    )


# ========== No Active Escalations Message ==========


def get_no_active_escalations_text() -> str:
    """
    Генерирует текст сообщения, когда нет активных эскалаций.
    
    Returns:
        Текст сообщения
    
    Requirements: FR-1.4.6
    """
    return (
        "✅ <b>Нет активных эскалаций</b>\n\n"
        "Все заявки обрабатываются в срок."
    )
