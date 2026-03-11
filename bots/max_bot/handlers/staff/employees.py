"""
Employee Management Handler for MAX Bot

Handles employee CRUD operations for administrators:
- Add new employees using MAX user ID
- List all employees with pagination
- View employee details
- Edit employee name and role
- Deactivate employees

Requirements: Employee Management Interface
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    AdminMenuPayload,
    EmployeeMenuPayload,
    EmployeeListPayload,
    EmployeeActionPayload,
    EmployeeRolePayload,
    EmployeeConfirmPayload,
    BackupManagerPayload,
    TransferTicketPayload,
    TransferClientsPayload,
    MainMenuActionPayload,
)
from database.models import Staff_Member, StaffRole, Action_Log, ActionType

logger = logging.getLogger(__name__)


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status: {e}", exc_info=True)
        return None


# ============================================================================
# Employee Management Menu
# ============================================================================


async def handle_employees_menu(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display employee management menu.
    
    Shows options to add or list employees.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: AdminMenuPayload with action="employees"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Employee menu access: max_user_id={max_user_id}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Clear FSM state
        await context.clear()
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Build employee management menu keyboard
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="➕ Добавить сотрудника",
                        payload=EmployeeMenuPayload(action="add").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="📋 Список сотрудников",
                        payload=EmployeeMenuPayload(action="list").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="◀️ Назад в админ-панель",
                        payload=AdminMenuPayload(action="employees_back").pack()
                    )
                ]
            ],
            inline=True
        )
        
        menu_text = (
            "👥 <b>Управление сотрудниками</b>\n\n"
            "В этом разделе вы можете:\n"
            "• Просматривать список всех сотрудников\n"
            "• Добавлять новых сотрудников в систему\n"
            "• Редактировать данные и роли сотрудников\n"
            "• Деактивировать сотрудников\n\n"
            "Выберите действие:"
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=menu_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed employees menu")
        
    except Exception as e:
        logger.error(f"Error showing employees menu: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке меню.",
            parse_mode="HTML"
        )


# ============================================================================
# Add Employee Flow
# ============================================================================


async def handle_add_employee_start(
    event: MessageCallback,
    payload: EmployeeMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Start add employee flow - prompt for MAX user ID.
    
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Set FSM state
        from bots.max_bot.states import EmployeeManagementStates
        await context.set_state(EmployeeManagementStates.adding_employee_id)
        
        # Prompt for MAX user ID
        prompt_text = (
            "➕ <b>Добавление сотрудника</b>\n\n"
            "Отправьте MAX ID нового сотрудника.\n\n"
            "<b>Пример ID:</b> <code>187660968</code>\n\n"
            "💡 <i>Как узнать MAX ID:</i>\n"
            "Попросите сотрудника отправить боту команду /my_id"
        )
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад",
                        payload=AdminMenuPayload(action="employees").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=prompt_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started add employee flow")
        
    except Exception as e:
        logger.error(f"Error starting add employee flow: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_employee_id_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle MAX user ID input for adding employee.
    
    Validates ID and checks if already registered.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Parse MAX user ID
        try:
            employee_max_id = int(text.strip())
        except ValueError:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неверный формат MAX ID. ID должен быть числом.\n\nПопробуйте еще раз:",
                parse_mode="HTML"
            )
            return
        
        # Check if already registered
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == employee_max_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        existing_staff = result.scalar_one_or_none()
        
        if existing_staff:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ Сотрудник с MAX ID <code>{employee_max_id}</code> уже зарегистрирован.\n\n"
                    f"<b>Имя:</b> {existing_staff.full_name}\n"
                    f"<b>Роль:</b> {existing_staff.staff_role.value}\n\n"
                    "Попробуйте другой ID:"
                ),
                parse_mode="HTML"
            )
            return
        
        # Store ID in FSM and prompt for name
        await context.update_data(employee_max_id=employee_max_id)
        
        # Set next state
        from bots.max_bot.states import EmployeeManagementStates
        await context.set_state(EmployeeManagementStates.adding_employee_name)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ MAX ID принят: <code>{employee_max_id}</code>\n\n"
                "Теперь введите <b>полное имя</b> сотрудника:\n\n"
                "<i>Например: Иванов Иван Иванович</i>"
            ),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} entered employee MAX ID: {employee_max_id}")
        
    except Exception as e:
        logger.error(f"Error handling employee ID input: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_employee_name_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle employee name input.
    
    Prompts for role selection.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Validate name
        full_name = text.strip()
        if len(full_name) < 3:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Имя слишком короткое. Введите полное имя (минимум 3 символа):",
                parse_mode="HTML"
            )
            return
        
        # Store name in FSM
        await context.update_data(employee_name=full_name)
        
        # Set next state
        from bots.max_bot.states import EmployeeManagementStates
        await context.set_state(EmployeeManagementStates.adding_employee_role)
        
        # Show role selection keyboard
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="👨‍💼 Менеджер",
                        payload=EmployeeRolePayload(role="manager").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="👨‍💻 Администратор",
                        payload=EmployeeRolePayload(role="administrator").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="❌ Отмена",
                        payload=AdminMenuPayload(action="employees").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Имя принято: <b>{full_name}</b>\n\n"
                "Выберите роль сотрудника:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} entered employee name: {full_name}")
        
    except Exception as e:
        logger.error(f"Error handling employee name input: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_employee_role_selection(
    event: MessageCallback,
    payload: EmployeeRolePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle employee role selection.
    
    Creates employee record and shows confirmation.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    role = payload.role
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get data from FSM
        data = await context.get_data()
        employee_max_id = data.get('employee_max_id')
        employee_name = data.get('employee_name')
        
        if not employee_max_id or not employee_name:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Данные не найдены. Начните процесс заново.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Map role string to StaffRole enum
        if role == "manager":
            staff_role = StaffRole.MANAGER
            role_display = "Менеджер"
        elif role == "administrator":
            staff_role = StaffRole.ADMINISTRATOR
            role_display = "Администратор"
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестная роль.",
                parse_mode="HTML"
            )
            return
        
        # Create employee record
        new_employee = Staff_Member(
            max_user_id=employee_max_id,
            full_name=employee_name,
            staff_role=staff_role,
            is_active=True,
            created_at=datetime.utcnow()
        )
        session.add(new_employee)
        await session.flush()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_ACTIVATED,
            staff_id=admin.id,
            action_details={
                "new_employee_id": new_employee.id,
                "new_employee_max_id": employee_max_id,
                "new_employee_name": employee_name,
                "new_employee_role": staff_role.value
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Clear FSM state
        await context.clear()
        
        # Show success message with back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ К списку сотрудников",
                        payload=EmployeeMenuPayload(action="list").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="◀️ В меню управления",
                        payload=AdminMenuPayload(action="employees").pack()
                    )
                ]
            ],
            inline=True
        )
        
        success_text = (
            "✅ <b>Сотрудник успешно добавлен!</b>\n\n"
            f"<b>MAX ID:</b> <code>{employee_max_id}</code>\n"
            f"<b>Имя:</b> {employee_name}\n"
            f"<b>Роль:</b> {role_display}\n\n"
            "Сотрудник может начать работу в системе."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=success_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {max_user_id} added employee: "
            f"id={new_employee.id}, max_id={employee_max_id}, name={employee_name}, role={staff_role.value}"
        )
        
    except Exception as e:
        logger.error(f"Error handling employee role selection: {e}", exc_info=True)
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при добавлении сотрудника. Попробуйте позже.",
            parse_mode="HTML"
        )


# ============================================================================
# List Employees
# ============================================================================


async def handle_list_employees(
    event: MessageCallback,
    payload: EmployeeMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    page: int = 0
) -> None:
    """
    Display list of employees with pagination.
    
    Shows 5 employees per page.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get all active employees
        stmt = select(Staff_Member).where(
            Staff_Member.is_active == True
        ).order_by(Staff_Member.full_name)
        result = await session.execute(stmt)
        all_employees = result.scalars().all()
        
        if not all_employees:
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад",
                            payload=AdminMenuPayload(action="employees").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📋 <b>Список сотрудников</b>\n\n<i>Нет активных сотрудников.</i>",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Pagination
        page_size = 5
        total_pages = (len(all_employees) + page_size - 1) // page_size
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_employees = all_employees[start_idx:end_idx]
        
        # Build employee list text
        lines = [
            f"📋 <b>Список сотрудников</b> (стр. {page + 1}/{total_pages})\n"
        ]
        
        for emp in page_employees:
            role_emoji = "👨‍💼" if emp.staff_role == StaffRole.MANAGER else "👨‍💻"
            lines.append(
                f"{role_emoji} <b>{emp.full_name}</b>\n"
                f"   ID: <code>{emp.max_user_id or 'N/A'}</code> | {emp.staff_role.value}"
            )
        
        list_text = "\n".join(lines)
        
        # Build keyboard with employee buttons and pagination
        buttons = []
        
        # Employee buttons - mark current user with emoji
        for emp in page_employees:
            is_current_user = emp.max_user_id == max_user_id
            button_text = f"👤 {emp.full_name}"
            if is_current_user:
                button_text = f"⭐ {emp.full_name} (Это вы)"
            
            buttons.append([
                KeyboardButton(
                    text=button_text,
                    payload=EmployeeActionPayload(action="view", employee_id=emp.id).pack()
                )
            ])
        
        # Pagination row
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(
                    KeyboardButton(
                        text="⬅️ Назад",
                        payload=EmployeeListPayload(action="prev", page=page - 1).pack()
                    )
                )
            if page < total_pages - 1:
                nav_row.append(
                    KeyboardButton(
                        text="Вперед ➡️",
                        payload=EmployeeListPayload(action="next", page=page + 1).pack()
                    )
                )
            if nav_row:
                buttons.append(nav_row)
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ В меню управления",
                payload=AdminMenuPayload(action="employees").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=list_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed employee list, page {page}")
        
    except Exception as e:
        logger.error(f"Error listing employees: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка.",
            parse_mode="HTML"
        )


async def handle_employee_list_pagination(
    event: MessageCallback,
    payload: EmployeeListPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Handle pagination in employee list."""
    # Create a fake EmployeeMenuPayload to reuse handle_list_employees
    fake_payload = EmployeeMenuPayload(action="list")
    await handle_list_employees(
        event=event,
        payload=fake_payload,
        context=context,
        session=session,
        messenger_adapter=messenger_adapter,
        page=payload.page
    )


# ========== Employee Actions (View/Edit/Deactivate) ==========


async def handle_employee_action(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle employee action buttons (view/edit/deactivate).
    
    Routes to appropriate handler based on action type.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action and staff_id
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: Employee Management Interface
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Route based on action
        if payload.action == "view":
            await show_employee_details(
                chat_id=chat_id,
                staff_id=payload.employee_id,
                max_user_id=max_user_id,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "edit_name":
            await handle_edit_name_start(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "edit_signature":
            await handle_edit_signature_start(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "edit_role":
            await handle_edit_role_start(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "deactivate":
            await handle_deactivate_confirmation(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "confirm_deactivate":
            await handle_confirm_deactivate(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "activate":
            await handle_activate_employee(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "set_duty_support":
            await handle_set_duty_support(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "unset_duty_support":
            await handle_unset_duty_support(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "backup_config":
            # Route to backup manager config
            backup_payload = BackupManagerPayload(action="config", employee_id=payload.employee_id)
            await handle_backup_manager_config(
                event=event,
                payload=backup_payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        elif payload.action == "transfer_clients":
            # Route to client transfer
            transfer_payload = TransferClientsPayload(action="start", source_manager_id=payload.employee_id)
            await handle_transfer_clients_start(
                event=event,
                payload=transfer_payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        else:
            logger.warning(f"Unknown employee action: {payload.action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
        
        logger.info(f"Administrator {max_user_id} performed action '{payload.action}' on staff {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error handling employee action: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def show_employee_details(
    chat_id: int,
    staff_id: int,
    max_user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show detailed information about an employee.

    Args:
        chat_id: Chat ID to send message to
        staff_id: Staff member ID
        max_user_id: MAX user ID of the admin viewing the details
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    try:
        # Get employee details
        stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()

        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return

        # Check if this employee is duty support
        from database.models import System_Settings
        duty_stmt = select(System_Settings).where(System_Settings.key == "duty_support_account")
        duty_result = await session.execute(duty_stmt)
        duty_setting = duty_result.scalar_one_or_none()
        is_duty_support = duty_setting and duty_setting.value and int(duty_setting.value) == staff_id

        # Format employee details
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }

        status_emoji = "✅" if employee.is_active else "❌"
        status_text = "Активен" if employee.is_active else "Деактивирован"

        details_text = (
            f"👤 <b>Карточка сотрудника</b>\n\n"
            f"<b>ID:</b> {employee.id}\n"
            f"<b>Имя:</b> {employee.full_name}\n"
            f"<b>MAX ID:</b> <code>{employee.max_user_id}</code>\n"
            f"<b>Роль:</b> {role_names.get(employee.staff_role, employee.staff_role.value)}\n"
            f"<b>Подпись:</b> {employee.position or 'не указана'}\n"
            f"<b>Статус:</b> {status_emoji} {status_text}\n"
        )

        if employee.created_at:
            details_text += f"<b>Добавлен:</b> {employee.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        # Add duty support status
        details_text += f"\n⚙️ <b>Дежурный аккаунт ТП:</b> {'✅ Да' if is_duty_support else '❌ Нет'}\n"

        # Add backup managers info
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            details_text += "\n🛡 <b>Резервные менеджеры:</b>\n"

            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_1_id)
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    details_text += f"Резерв 1: {backup1.full_name}\n"
                else:
                    details_text += "Резерв 1: Не назначен\n"

            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_2_id)
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    details_text += f"Резерв 2: {backup2.full_name}\n"
                else:
                    details_text += "Резерв 2: Не назначен\n"

        # Check if viewing own profile
        is_own_profile = employee.max_user_id == max_user_id

        # Create action buttons
        buttons = []

        if employee.is_active:
            # Edit buttons row 1 - always show name and signature edit
            buttons.append([
                KeyboardButton(
                    text="✏️ Изменить имя",
                    payload=EmployeeActionPayload(action="edit_name", employee_id=staff_id).pack()
                ),
                KeyboardButton(
                    text="📝 Подпись",
                    payload=EmployeeActionPayload(action="edit_signature", employee_id=staff_id).pack()
                )
            ])

            # Edit buttons row 2 - hide role change for admin viewing own profile
            if not (is_own_profile and employee.staff_role == StaffRole.ADMINISTRATOR):
                buttons.append([
                    KeyboardButton(
                        text="🔄 Изменить роль",
                        payload=EmployeeActionPayload(action="edit_role", employee_id=staff_id).pack()
                    )
                ])

            # Duty support button
            if is_duty_support:
                buttons.append([
                    KeyboardButton(
                        text="⚙️ Снять с дежурства ТП",
                        payload=EmployeeActionPayload(action="unset_duty_support", employee_id=staff_id).pack()
                    )
                ])
            else:
                buttons.append([
                    KeyboardButton(
                        text="⚙️ Назначить дежурным ТП",
                        payload=EmployeeActionPayload(action="set_duty_support", employee_id=staff_id).pack()
                    )
                ])

            # Backup managers button
            buttons.append([
                KeyboardButton(
                    text="🛡 Резервные менеджеры",
                    payload=EmployeeActionPayload(action="backup_config", employee_id=staff_id).pack()
                )
            ])

            # Transfer clients button (only for managers)
            if employee.staff_role == StaffRole.MANAGER:
                buttons.append([
                    KeyboardButton(
                        text="👥 Передать клиентов",
                        payload=EmployeeActionPayload(action="transfer_clients", employee_id=staff_id).pack()
                    )
                ])

            # Deactivate button - hide for admin viewing own profile
            if not (is_own_profile and employee.staff_role == StaffRole.ADMINISTRATOR):
                buttons.append([
                    KeyboardButton(
                        text="🚫 Деактивировать",
                        payload=EmployeeActionPayload(action="deactivate", employee_id=staff_id).pack()
                    )
                ])
        else:
            # Activate button for deactivated employees
            buttons.append([
                KeyboardButton(
                    text="✅ Активировать",
                    payload=EmployeeActionPayload(action="activate", employee_id=staff_id).pack()
                )
            ])

        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ К списку сотрудников",
                payload=EmployeeMenuPayload(action="list").pack()
            )
        ])

        keyboard = Keyboard(buttons=buttons, inline=True)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=details_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error showing employee details: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке информации о сотруднике.",
            parse_mode="HTML"
        )






# ========== Edit Employee Name ==========


async def handle_edit_name_start(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Edit Name" button press.
    
    Prompts administrator to enter new name.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action="edit_name"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Get employee details
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Store employee ID in FSM data
        await context.update_data(editing_employee_id=payload.employee_id, old_name=employee.full_name)
        
        # Set FSM state to wait for new name
        from bots.max_bot.states import EmployeeManagementStates
        await context.set_state(EmployeeManagementStates.editing_employee_name)
        
        # Create cancel keyboard
        buttons = [[
            KeyboardButton(
                text="❌ Отмена",
                payload=EmployeeActionPayload(action="view", employee_id=payload.employee_id).pack()
            )
        ]]
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✏️ <b>Изменение имени</b>\n\n"
                f"Сотрудник: {employee.full_name}\n"
                f"Текущее имя: <b>{employee.full_name}</b>\n\n"
                f"Введите новое имя:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing name for employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error starting name edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_employee_name_edit_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle new name text input.
    
    Updates the employee name and displays confirmation with employee card.
    Uses replace_message pattern.
    
    Args:
        event: MessageCreated event
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    max_user_id = event.message.sender.user_id
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к административной панели.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get new name text
        new_name = event.message.body.text.strip()
        
        if len(new_name) < 2:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Имя слишком короткое. Минимум 2 символа.",
                parse_mode="HTML"
            )
            return
        
        if len(new_name) > 100:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Имя слишком длинное. Максимум 100 символов.",
                parse_mode="HTML"
            )
            return
        
        # Get employee ID from FSM data
        data = await context.get_data()
        employee_id = data.get("editing_employee_id")
        
        if not employee_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: данные не найдены. Начните заново.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Update name
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        old_name = employee.full_name
        employee.full_name = new_name
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "employee_id": employee_id,
                "field": "name",
                "old_value": old_name,
                "new_value": new_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Clear FSM state
        await context.clear()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Имя успешно обновлено: <b>{new_name}</b>",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} updated name for employee {employee_id}: '{old_name}' -> '{new_name}'")
        
    except Exception as e:
        logger.error(f"Error handling name edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обновлении имени.",
            parse_mode="HTML"
        )
        await context.clear()


# ========== Edit Employee Role ==========


async def handle_edit_role_start(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Change Role" button press.
    
    Displays role selection keyboard.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action="edit_role"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Get employee details
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Role display names
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        current_role = role_names.get(employee.staff_role, employee.staff_role.value)
        
        # Create role selection keyboard
        buttons = []
        for role in [StaffRole.TECHNICAL_SUPPORT, StaffRole.MANAGER, StaffRole.ADMINISTRATOR]:
            if role != employee.staff_role:  # Don't show current role
                buttons.append([
                    KeyboardButton(
                        text=role_names[role],
                        payload=EmployeeRolePayload(
                            employee_id=payload.employee_id,
                            role=role.value
                        ).pack()
                    )
                ])
        
        # Cancel button
        buttons.append([
            KeyboardButton(
                text="❌ Отмена",
                payload=EmployeeActionPayload(action="view", employee_id=payload.employee_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"🔄 <b>Изменение роли</b>\n\n"
                f"Сотрудник: {employee.full_name}\n"
                f"Текущая роль: <b>{current_role}</b>\n\n"
                f"Выберите новую роль:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing role for employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error starting role edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_employee_role_change(
    event: MessageCallback,
    payload: EmployeeRolePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle role selection for editing existing employee.
    
    Updates employee role and shows confirmation.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeRolePayload with employee_id and new role
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Update role
        old_role = employee.staff_role
        new_role = StaffRole(payload.role)
        employee.staff_role = new_role
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "employee_id": payload.employee_id,
                "field": "role",
                "old_value": old_role.value,
                "new_value": new_role.value
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=payload.employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Role display names
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        # Send confirmation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Роль успешно изменена: <b>{role_names[new_role]}</b>",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} changed role for employee {payload.employee_id}: {old_role.value} -> {new_role.value}")
        
    except Exception as e:
        logger.error(f"Error changing employee role: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при изменении роли.",
            parse_mode="HTML"
        )


# ========== Deactivate Employee ==========


async def handle_deactivate_confirmation(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Deactivate" button press.
    
    Displays confirmation prompt before deactivating employee.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action="deactivate"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Get employee details
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Role display names
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        role_text = role_names.get(employee.staff_role, employee.staff_role.value)
        
        # Create confirmation keyboard
        buttons = [
            [
                KeyboardButton(
                    text="✅ Да, деактивировать",
                    payload=EmployeeActionPayload(action="confirm_deactivate", employee_id=payload.employee_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=EmployeeActionPayload(action="view", employee_id=payload.employee_id).pack()
                )
            ]
        ]
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>Подтверждение деактивации</b>\n\n"
                f"Сотрудник: {employee.full_name}\n"
                f"Должность: {role_text}\n\n"
                f"При деактивации:\n"
                f"• Сотрудник потеряет доступ к системе\n"
                f"• Все его активные заявки будут переведены в статус NEW\n"
                f"• Заявки будут сняты с назначения\n\n"
                f"Вы уверены?"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} requested deactivation confirmation for employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error showing deactivation confirmation: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_confirm_deactivate(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle deactivation confirmation.
    
    Deactivates the employee and reassigns their tickets.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action="confirm_deactivate"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Deactivate employee and reassign tickets
        from database.models import Ticket, TicketStatus
        
        # Count tickets to reassign
        tickets_stmt = select(Ticket).where(
            Ticket.assigned_to == payload.employee_id,
            Ticket.status.in_([TicketStatus.IN_PROGRESS, TicketStatus.PENDING])
        )
        tickets_result = await session.execute(tickets_stmt)
        tickets = tickets_result.scalars().all()
        reassigned_count = len(tickets)
        
        # Reassign tickets to NEW status and remove assignment
        for ticket in tickets:
            ticket.status = TicketStatus.NEW
            ticket.assigned_to = None
        
        # Deactivate employee
        employee.is_active = False
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_DEACTIVATED,
            staff_id=admin.id,
            action_details={
                "employee_id": payload.employee_id,
                "employee_name": employee.full_name,
                "reassigned_tickets": reassigned_count
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Role display names
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        role_text = role_names.get(employee.staff_role, employee.staff_role.value)
        
        # Create back button
        buttons = [[
            KeyboardButton(
                text="◀️ К списку сотрудников",
                payload=EmployeeMenuPayload(action="list").pack()
            )
        ]]
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Сотрудник деактивирован</b>\n\n"
                f"Имя: {employee.full_name}\n"
                f"Должность: {role_text}\n\n"
                f"Переназначено заявок: {reassigned_count}\n\n"
                f"Сотрудник больше не имеет доступа к системе."
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} deactivated employee {payload.employee_id}: reassigned {reassigned_count} tickets")
        
    except Exception as e:
        logger.error(f"Error deactivating employee: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при деактивации.",
            parse_mode="HTML"
        )


# ========== Activate Employee ==========


async def handle_activate_employee(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle employee activation.
    
    Activates a deactivated employee.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: EmployeeActionPayload with action="activate"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Activate employee
        employee.is_active = True
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_ACTIVATED,
            staff_id=admin.id,
            action_details={
                "employee_id": payload.employee_id,
                "employee_name": employee.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=payload.employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Сотрудник <b>{employee.full_name}</b> успешно активирован!",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} activated employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error activating employee: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при активации.",
            parse_mode="HTML"
        )



# ========== Edit Employee Signature ==========


async def handle_edit_signature_start(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Edit Signature" button press.
    
    Prompts administrator to enter new signature text.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Get employee details
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Store employee ID in FSM data
        await context.update_data(editing_employee_id=payload.employee_id, old_signature=employee.position)
        
        # Set FSM state to wait for new signature
        from bots.max_bot.states import EmployeeManagementStates
        await context.set_state(EmployeeManagementStates.editing_employee_signature)
        
        # Create cancel keyboard
        buttons = [[
            KeyboardButton(
                text="❌ Отмена",
                payload=EmployeeActionPayload(action="view", employee_id=payload.employee_id).pack()
            )
        ]]
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"📝 <b>Изменение подписи</b>\n\n"
                f"Сотрудник: {employee.full_name}\n"
                f"Текущая подпись: <b>{employee.position or 'не указана'}</b>\n\n"
                f"Введите новую подпись:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing signature for employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error starting signature edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_employee_signature_edit_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle new signature text input.
    
    Updates the employee signature and displays confirmation.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к административной панели.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get new signature text
        new_signature = event.message.body.text.strip()
        
        if len(new_signature) < 3:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Подпись слишком короткая. Минимум 3 символа.",
                parse_mode="HTML"
            )
            return
        
        if len(new_signature) > 128:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Подпись слишком длинная. Максимум 128 символов.",
                parse_mode="HTML"
            )
            return
        
        # Get employee ID from FSM data
        data = await context.get_data()
        employee_id = data.get("editing_employee_id")
        
        if not employee_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: данные не найдены. Начните заново.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Update signature
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        old_signature = employee.position
        employee.position = new_signature
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "employee_id": employee_id,
                "field": "signature",
                "old_value": old_signature,
                "new_value": new_signature
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Clear FSM state
        await context.clear()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Подпись успешно обновлена: <b>{new_signature}</b>",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} updated signature for employee {employee_id}: '{old_signature}' -> '{new_signature}'")
        
    except Exception as e:
        logger.error(f"Error handling signature edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обновлении подписи.",
            parse_mode="HTML"
        )
        await context.clear()



# ========== Duty Support Account ==========


async def handle_set_duty_support(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Set as Duty Support" button press.
    
    Designates the selected employee as the duty support account for extended hours.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        if not employee.is_active:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Нельзя назначить дежурным деактивированного сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Update duty support setting
        from database.models import System_Settings
        
        # Check if setting exists
        setting_stmt = select(System_Settings).where(System_Settings.key == "duty_support_account")
        setting_result = await session.execute(setting_stmt)
        setting = setting_result.scalar_one_or_none()
        
        if setting:
            setting.value = str(payload.employee_id)
        else:
            setting = System_Settings(
                key="duty_support_account",
                value=str(payload.employee_id)
            )
            session.add(setting)
        
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "action": "set_duty_support",
                "employee_id": payload.employee_id,
                "employee_name": employee.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=payload.employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Сотрудник <b>{employee.full_name}</b> назначен дежурным аккаунтом техподдержки",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} set employee {payload.employee_id} as duty support")
        
    except Exception as e:
        logger.error(f"Error setting duty support: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при назначении.",
            parse_mode="HTML"
        )


async def handle_unset_duty_support(
    event: MessageCallback,
    payload: EmployeeActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Unset as Duty Support" button press.
    
    Removes the duty support designation from the selected employee.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Clear duty support setting
        from database.models import System_Settings
        
        setting_stmt = select(System_Settings).where(System_Settings.key == "duty_support_account")
        setting_result = await session.execute(setting_stmt)
        setting = setting_result.scalar_one_or_none()
        
        if setting:
            setting.value = ""
            await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "action": "unset_duty_support",
                "employee_id": payload.employee_id,
                "employee_name": employee.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated employee card
        await show_employee_details(
            chat_id=chat_id,
            staff_id=payload.employee_id,
            max_user_id=max_user_id,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Сотрудник <b>{employee.full_name}</b> снят с дежурства техподдержки",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} removed duty support from employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error unsetting duty support: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при снятии с дежурства.",
            parse_mode="HTML"
        )



# ========== Backup Managers ==========


async def handle_backup_manager_config(
    event: MessageCallback,
    payload: BackupManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Handle backup manager configuration interface."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.bo


# ========== Backup Managers ==========


async def handle_backup_manager_config(
    event: MessageCallback,
    payload: BackupManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle backup manager configuration interface.
    
    Shows current backup managers and options to configure them.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Build configuration text
        config_text = (
            f"🛡 <b>Настройка резервных менеджеров</b>\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Должность: {employee.position or 'не указана'}\n\n"
            f"Резервные менеджеры получают эскалированные заявки, "
            f"если основной сотрудник не отвечает в течение установленного времени.\n\n"
        )
        
        # Add current backup managers
        if employee.backup_manager_1_id:
            backup1_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_1_id)
            backup1_result = await session.execute(backup1_stmt)
            backup1 = backup1_result.scalar_one_or_none()
            if backup1:
                config_text += f"<b>Резерв 1:</b> {backup1.full_name} ({backup1.position or 'не указана'})\n"
            else:
                config_text += "<b>Резерв 1:</b> Не назначен\n"
        else:
            config_text += "<b>Резерв 1:</b> Не назначен\n"
        
        if employee.backup_manager_2_id:
            backup2_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_2_id)
            backup2_result = await session.execute(backup2_stmt)
            backup2 = backup2_result.scalar_one_or_none()
            if backup2:
                config_text += f"<b>Резерв 2:</b> {backup2.full_name} ({backup2.position or 'не указана'})\n"
            else:
                config_text += "<b>Резерв 2:</b> Не назначен\n"
        else:
            config_text += "<b>Резерв 2:</b> Не назначен\n"
        
        # Create buttons
        buttons = []
        
        # Slot 1 button
        if employee.backup_manager_1_id:
            buttons.append([
                KeyboardButton(
                    text="🔄 Изменить резерв 1",
                    payload=BackupManagerPayload(action="select_slot", employee_id=payload.employee_id, slot=1).pack()
                ),
                KeyboardButton(
                    text="❌ Удалить резерв 1",
                    payload=BackupManagerPayload(action="remove", employee_id=payload.employee_id, slot=1).pack()
                )
            ])
        else:
            buttons.append([
                KeyboardButton(
                    text="➕ Назначить резерв 1",
                    payload=BackupManagerPayload(action="select_slot", employee_id=payload.employee_id, slot=1).pack()
                )
            ])
        
        # Slot 2 button
        if employee.backup_manager_2_id:
            buttons.append([
                KeyboardButton(
                    text="🔄 Изменить резерв 2",
                    payload=BackupManagerPayload(action="select_slot", employee_id=payload.employee_id, slot=2).pack()
                ),
                KeyboardButton(
                    text="❌ Удалить резерв 2",
                    payload=BackupManagerPayload(action="remove", employee_id=payload.employee_id, slot=2).pack()
                )
            ])
        else:
            buttons.append([
                KeyboardButton(
                    text="➕ Назначить резерв 2",
                    payload=BackupManagerPayload(action="select_slot", employee_id=payload.employee_id, slot=2).pack()
                )
            ])
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ Назад к карточке",
                payload=EmployeeActionPayload(action="view", employee_id=payload.employee_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=config_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} opened backup config for employee {payload.employee_id}")
        
    except Exception as e:
        logger.error(f"Error showing backup config: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_backup_slot_selection(
    event: MessageCallback,
    payload: BackupManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle backup slot selection.
    
    Shows list of available staff to assign as backup manager.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get available staff (active, not the employee themselves, not already assigned to other slot)
        # Exclude the backup manager from the other slot
        exclude_ids = [payload.employee_id]
        
        if payload.slot == 1 and employee.backup_manager_2_id:
            # Selecting for slot 1, exclude current slot 2 manager
            exclude_ids.append(employee.backup_manager_2_id)
        elif payload.slot == 2 and employee.backup_manager_1_id:
            # Selecting for slot 2, exclude current slot 1 manager
            exclude_ids.append(employee.backup_manager_1_id)
        
        available_stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.id.not_in(exclude_ids)
            )
        ).order_by(Staff_Member.full_name)
        available_result = await session.execute(available_stmt)
        available_staff = list(available_result.scalars().all())
        
        if not available_staff:
            # No staff available - show message with back button
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад к настройкам",
                            payload=BackupManagerPayload(action="config", employee_id=payload.employee_id).pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нет доступных сотрудников для назначения.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Create selection buttons
        buttons = []
        
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "ТП",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Админ"
        }
        
        for staff in available_staff:
            role_text = role_names.get(staff.staff_role, staff.staff_role.value)
            button_text = f"{staff.full_name} ({role_text})"
            
            buttons.append([
                KeyboardButton(
                    text=button_text,
                    payload=BackupManagerPayload(
                        action="assign",
                        employee_id=payload.employee_id,
                        slot=payload.slot,
                        backup_id=staff.id
                    ).pack()
                )
            ])
        
        # Cancel button
        buttons.append([
            KeyboardButton(
                text="❌ Отмена",
                payload=BackupManagerPayload(action="config", employee_id=payload.employee_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"🛡 <b>Выбор резервного менеджера</b>\n\n"
                f"Сотрудник: {employee.full_name}\n"
                f"Слот: Резерв {payload.slot}\n\n"
                f"Выберите сотрудника из списка:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} selecting backup for employee {payload.employee_id}, slot {payload.slot}")
        
    except Exception as e:
        logger.error(f"Error showing backup selection: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_backup_manager_assignment(
    event: MessageCallback,
    payload: BackupManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle backup manager assignment.
    
    Assigns selected staff as backup manager.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get backup manager
        backup_stmt = select(Staff_Member).where(Staff_Member.id == payload.backup_id)
        backup_result = await session.execute(backup_stmt)
        backup_manager = backup_result.scalar_one_or_none()
        
        if not backup_manager:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Резервный менеджер не найден.",
                parse_mode="HTML"
            )
            return
        
        # Validate: cannot assign the same person to both slots
        if payload.slot == 1 and employee.backup_manager_2_id == payload.backup_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Сотрудник <b>{backup_manager.full_name}</b> уже назначен резервным менеджером в слоте 2. Один сотрудник не может быть назначен в оба слота.",
                parse_mode="HTML"
            )
            return
        elif payload.slot == 2 and employee.backup_manager_1_id == payload.backup_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Сотрудник <b>{backup_manager.full_name}</b> уже назначен резервным менеджером в слоте 1. Один сотрудник не может быть назначен в оба слота.",
                parse_mode="HTML"
            )
            return
        
        # Assign backup manager
        if payload.slot == 1:
            employee.backup_manager_1_id = payload.backup_id
        elif payload.slot == 2:
            employee.backup_manager_2_id = payload.backup_id
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неверный номер слота.",
                parse_mode="HTML"
            )
            return
        
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=admin.id,
            action_details={
                "action": "assign_backup_manager",
                "employee_id": payload.employee_id,
                "slot": payload.slot,
                "backup_manager_id": payload.backup_id,
                "backup_manager_name": backup_manager.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated config
        await handle_backup_manager_config(
            event=event,
            payload=BackupManagerPayload(action="config", employee_id=payload.employee_id),
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Резервный менеджер назначен: <b>{backup_manager.full_name}</b> (слот {payload.slot})",
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} assigned backup manager {payload.backup_id} to employee {payload.employee_id}, slot {payload.slot}")
        
    except Exception as e:
        logger.error(f"Error assigning backup manager: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при назначении.",
            parse_mode="HTML"
        )


async def handle_backup_manager_removal(
    event: MessageCallback,
    payload: BackupManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle backup manager removal.
    
    Removes backup manager from specified slot.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get employee
        stmt = select(Staff_Member).where(Staff_Member.id == payload.employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Remove backup manager
        removed_name = None
        if payload.slot == 1 and employee.backup_manager_1_id:
            backup_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_1_id)
            backup_result = await session.execute(backup_stmt)
            backup = backup_result.scalar_one_or_none()
            removed_name = backup.full_name if backup else "Неизвестно"
            employee.backup_manager_1_id = None
        elif payload.slot == 2 and employee.backup_manager_2_id:
            backup_stmt = select(Staff_Member).where(Staff_Member.id == employee.backup_manager_2_id)
            backup_result = await session.execute(backup_stmt)
            backup = backup_result.scalar_one_or_none()
            removed_name = backup.full_name if backup else "Неизвестно"
            employee.backup_manager_2_id = None
        
        await session.commit()
        
        # Log action
        if removed_name:
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "action": "remove_backup_manager",
                    "employee_id": payload.employee_id,
                    "slot": payload.slot,
                    "removed_backup_name": removed_name
                }
            )
            session.add(action_log)
            await session.commit()
        
        # Show updated config
        await handle_backup_manager_config(
            event=event,
            payload=BackupManagerPayload(action="config", employee_id=payload.employee_id),
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        # Send confirmation
        if removed_name:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ Резервный менеджер удален: <b>{removed_name}</b> (слот {payload.slot})",
                parse_mode="HTML"
            )
        
        logger.info(f"Administrator {max_user_id} removed backup manager from employee {payload.employee_id}, slot {payload.slot}")
        
    except Exception as e:
        logger.error(f"Error removing backup manager: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при удалении.",
            parse_mode="HTML"
        )



# ========== Transfer Tickets ==========


async def handle_transfer_ticket_start(
    event: MessageCallback,
    payload: TransferTicketPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket transfer start.
    
    Shows list of available staff to transfer ticket to.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get ticket
        from database.models import Ticket
        ticket_stmt = select(Ticket).where(Ticket.id == payload.ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get available staff (active, excluding current assignee)
        available_stmt = select(Staff_Member).where(
            Staff_Member.is_active == True
        )
        if ticket.assigned_to:
            available_stmt = available_stmt.where(Staff_Member.id != ticket.assigned_to)
        
        available_stmt = available_stmt.order_by(Staff_Member.full_name)
        available_result = await session.execute(available_stmt)
        available_staff = list(available_result.scalars().all())
        
        if not available_staff:
            # No staff available - show message with back button
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад",
                            payload=MainMenuActionPayload(action="back").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нет доступных сотрудников для передачи заявки.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Create selection buttons
        buttons = []
        
        role_names = {
            StaffRole.TECHNICAL_SUPPORT: "ТП",
            StaffRole.MANAGER: "Менеджер",
            StaffRole.ADMINISTRATOR: "Админ"
        }
        
        for staff in available_staff:
            role_text = role_names.get(staff.staff_role, staff.staff_role.value)
            button_text = f"{staff.full_name} ({role_text})"
            
            buttons.append([
                KeyboardButton(
                    text=button_text,
                    payload=TransferTicketPayload(
                        action="confirm",
                        ticket_id=payload.ticket_id,
                        target_employee_id=staff.id
                    ).pack()
                )
            ])
        
        # Cancel button
        buttons.append([
            KeyboardButton(
                text="❌ Отмена",
                payload=MainMenuActionPayload(action="back").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Get ticket type display
        ticket_type_names = {
            "INVOICE": "Счет",
            "TECHNICAL_SUPPORT": "Техподдержка",
            "RENEWAL": "Продление"
        }
        ticket_type = ticket_type_names.get(ticket.ticket_type.value if hasattr(ticket.ticket_type, 'value') else str(ticket.ticket_type), str(ticket.ticket_type))
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"🔄 <b>Передача заявки</b>\n\n"
                f"Заявка #{ticket.id}\n"
                f"Тип: {ticket_type}\n\n"
                f"Выберите сотрудника для передачи:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started ticket transfer for ticket {payload.ticket_id}")
        
    except Exception as e:
        logger.error(f"Error starting ticket transfer: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_transfer_ticket_confirm(
    event: MessageCallback,
    payload: TransferTicketPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket transfer confirmation.
    
    Transfers ticket to selected employee.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get ticket
        from database.models import Ticket, TicketStatus
        ticket_stmt = select(Ticket).where(Ticket.id == payload.ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get target employee
        target_stmt = select(Staff_Member).where(Staff_Member.id == payload.target_employee_id)
        target_result = await session.execute(target_stmt)
        target_employee = target_result.scalar_one_or_none()
        
        if not target_employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Transfer ticket
        old_assignee_id = ticket.assigned_to
        ticket.assigned_to = payload.target_employee_id
        ticket.status = TicketStatus.IN_PROGRESS
        await session.commit()
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.TICKET_TRANSFERRED,
            staff_id=admin.id,
            ticket_id=payload.ticket_id,
            action_details={
                "from_employee_id": old_assignee_id,
                "to_employee_id": payload.target_employee_id,
                "to_employee_name": target_employee.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Заявка передана</b>\n\n"
                f"Заявка #{ticket.id}\n"
                f"Новый исполнитель: {target_employee.full_name}"
            ),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} transferred ticket {payload.ticket_id} to employee {payload.target_employee_id}")
        
    except Exception as e:
        logger.error(f"Error confirming ticket transfer: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при передаче заявки.",
            parse_mode="HTML"
        )


# ========== Transfer Clients ==========


async def handle_transfer_clients_start(
    event: MessageCallback,
    payload: TransferClientsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle client transfer start.
    
    Shows list of available managers to transfer clients to.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get source manager
        source_stmt = select(Staff_Member).where(Staff_Member.id == payload.source_manager_id)
        source_result = await session.execute(source_stmt)
        source_manager = source_result.scalar_one_or_none()
        
        if not source_manager:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Менеджер не найден.",
                parse_mode="HTML"
            )
            return
        
        # Verify source is a manager
        if source_manager.staff_role != StaffRole.MANAGER:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Передача клиентов доступна только для менеджеров.",
                parse_mode="HTML"
            )
            return
        
        # Get available managers (active, excluding source)
        managers_stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.staff_role == StaffRole.MANAGER,
                Staff_Member.id != payload.source_manager_id
            )
        ).order_by(Staff_Member.full_name)
        managers_result = await session.execute(managers_stmt)
        available_managers = list(managers_result.scalars().all())
        
        if not available_managers:
            # No managers available - show message with back button
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад к карточке",
                            payload=EmployeeActionPayload(action="view", employee_id=payload.source_manager_id).pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нет доступных менеджеров для передачи клиентов.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Create selection buttons
        buttons = []
        
        for manager in available_managers:
            buttons.append([
                KeyboardButton(
                    text=manager.full_name,
                    payload=TransferClientsPayload(
                        action="confirm",
                        source_manager_id=payload.source_manager_id,
                        target_manager_id=manager.id
                    ).pack()
                )
            ])
        
        # Cancel button
        buttons.append([
            KeyboardButton(
                text="❌ Отмена",
                payload=EmployeeActionPayload(action="view", employee_id=payload.source_manager_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"👤 <b>Передача всех клиентов</b>\n\n"
                f"От менеджера: {source_manager.full_name}\n\n"
                f"Выберите целевого менеджера:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started client transfer from manager {payload.source_manager_id}")
        
    except Exception as e:
        logger.error(f"Error starting client transfer: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_transfer_clients_confirm(
    event: MessageCallback,
    payload: TransferClientsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle client transfer confirmation.
    
    Transfers all clients from source manager to target manager via i-TAT API.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению сотрудниками.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get both managers
        source_stmt = select(Staff_Member).where(Staff_Member.id == payload.source_manager_id)
        source_result = await session.execute(source_stmt)
        source_manager = source_result.scalar_one_or_none()
        
        target_stmt = select(Staff_Member).where(Staff_Member.id == payload.target_manager_id)
        target_result = await session.execute(target_stmt)
        target_manager = target_result.scalar_one_or_none()
        
        if not source_manager or not target_manager:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Менеджер не найден.",
                parse_mode="HTML"
            )
            return
        
        # Show confirmation with warning
        buttons = [
            [
                KeyboardButton(
                    text="✅ Да, передать всех клиентов",
                    payload=TransferClientsPayload(
                        action="execute",
                        source_manager_id=payload.source_manager_id,
                        target_manager_id=payload.target_manager_id
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=EmployeeActionPayload(action="view", employee_id=payload.source_manager_id).pack()
                )
            ]
        ]
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>Подтверждение передачи клиентов</b>\n\n"
                f"Эта операция передаст ВСЕХ клиентов (по ИНН) от выбранного менеджера "
                f"другому менеджеру через API i-TAT.\n\n"
                f"<b>От:</b> {source_manager.full_name}\n"
                f"<b>Кому:</b> {target_manager.full_name}\n\n"
                f"Вы уверены?"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewing transfer confirmation: from={payload.source_manager_id} to={payload.target_manager_id}")
        
    except Exception as e:
        logger.error(f"Error showing transfer confirmation: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )
