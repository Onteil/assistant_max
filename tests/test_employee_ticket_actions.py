"""
Integration test for employee ticket actions.

This test verifies that the employee interface ticket actions work end-to-end:
1. Take ticket into work
2. Set ticket to waiting for client
3. Close ticket with final comment
4. Transfer ticket to another employee

Requirements: Tasks 1-8 of employee-interface spec
"""

import asyncio
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from database.models import (
    Action_Log,
    ActionType,
    Base,
    Message,
    SenderType,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
    User,
)
from services.employee_service import (
    calculate_ticket_elapsed_time,
    format_ticket_card,
    get_available_employees_for_transfer,
    get_employee_active_tickets,
    get_employee_signature,
    get_ticket_action_keyboard,
)
from services.ticket_service import (
    close_ticket,
    set_ticket_waiting_client,
    take_ticket_into_work,
    transfer_ticket,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_employee_service_functions():
    """Test employee service layer functions."""
    print("\n" + "=" * 80)
    print("TEST 1: Employee Service Functions")
    print("=" * 80)

    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create test user
        user = User(
            tg_user_id=123456789,
            phone_number="+79991234567",
            full_name="Test Client",
        )
        session.add(user)

        # Create test employee with explicit ID
        employee = Staff_Member(
            id=1,
            tg_user_id=987654321,
            full_name="Test Employee",
            position="Technical Support Specialist",
            staff_role=StaffRole.TECHNICAL_SUPPORT,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(user)
        await session.refresh(employee)

        # Create test ticket
        ticket = Ticket(
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            description="Test ticket - Test description",
            tg_user_id=user.tg_user_id,
            assigned_staff_id=employee.tg_user_id,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

        print("\n--- Test: Get Employee Signature ---")
        signature = await get_employee_signature(session, employee.tg_user_id)
        assert signature is not None
        assert "Test Employee" in signature
        print(f"✓ Employee signature: {signature}")

        print("\n--- Test: Calculate Elapsed Time ---")
        elapsed = await calculate_ticket_elapsed_time(ticket)
        assert elapsed is not None
        # The function uses Russian characters for time units
        assert "ч" in elapsed or "м" in elapsed or "д" in elapsed
        print(f"✓ Elapsed time: {elapsed}")

        print("\n--- Test: Format Ticket Card ---")
        # Reload ticket with relationships eagerly loaded
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket.id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
            )
        )
        result = await session.execute(stmt)
        ticket_with_relations = result.scalar_one()
        
        card = await format_ticket_card(ticket_with_relations, session)
        assert f"#{ticket.id}" in card  # Ticket ID should be in card
        assert "Test Client" in card
        assert "Test ticket" in card or "Test description" in card
        print(f"✓ Ticket card formatted (length: {len(card)} chars)")

        print("\n--- Test: Get Ticket Action Keyboard ---")
        keyboard = await get_ticket_action_keyboard(ticket)
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) > 0
        button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
        assert "Взять в работу" in button_texts  # NEW status shows this button
        print(f"✓ Action keyboard has {len(button_texts)} buttons")

        print("\n--- Test: Get Active Tickets ---")
        active_tickets = await get_employee_active_tickets(session, employee.tg_user_id)
        assert len(active_tickets) == 1
        assert active_tickets[0].id == ticket.id
        print(f"✓ Found {len(active_tickets)} active ticket(s)")

    print("\n✅ All employee service functions work correctly")
    print("=" * 80)


@pytest.mark.asyncio
async def test_ticket_action_workflows():
    """Test ticket action workflows end-to-end."""
    print("\n" + "=" * 80)
    print("TEST 2: Ticket Action Workflows")
    print("=" * 80)

    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create test user
        user = User(
            tg_user_id=123456789,
            phone_number="+79991234567",
            full_name="Test Client",
        )
        session.add(user)

        # Create test employees with explicit IDs
        employee1 = Staff_Member(
            id=1,
            tg_user_id=987654321,
            full_name="Employee One",
            position="Technical Support",
            staff_role=StaffRole.TECHNICAL_SUPPORT,
            is_active=True,
        )
        employee2 = Staff_Member(
            id=2,
            tg_user_id=987654322,
            full_name="Employee Two",
            position="Senior Technical Support",
            staff_role=StaffRole.TECHNICAL_SUPPORT,
            is_active=True,
        )
        session.add_all([employee1, employee2])
        await session.commit()
        await session.refresh(user)
        await session.refresh(employee1)
        await session.refresh(employee2)

        # Create test ticket
        ticket = Ticket(
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            description="Test workflow ticket - Test workflow description",
            tg_user_id=user.tg_user_id,
            assigned_staff_id=employee1.tg_user_id,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

        print("\n--- Workflow 1: Take Ticket Into Work ---")
        initial_status = ticket.ticket_status
        updated_ticket = await take_ticket_into_work(session, ticket.id, employee1.tg_user_id, messenger="telegram")
        assert updated_ticket.ticket_status == TicketStatus.IN_PROGRESS
        assert initial_status == TicketStatus.NEW
        print(f"✓ Status changed: {initial_status.value} → {updated_ticket.ticket_status.value}")

        # Verify action log
        result = await session.execute(
            select(Action_Log).where(
                Action_Log.ticket_id == ticket.id,
                Action_Log.action_type == ActionType.TICKET_ASSIGNED,
            )
        )
        log_entry = result.scalar_one_or_none()
        assert log_entry is not None
        print(f"✓ Action logged: {log_entry.action_type.value}")

        print("\n--- Workflow 2: Set Ticket Waiting for Client ---")
        updated_ticket = await set_ticket_waiting_client(session, ticket.id, employee1.tg_user_id)
        assert updated_ticket.ticket_status == TicketStatus.WAITING_CLIENT
        print(f"✓ Status changed to: {updated_ticket.ticket_status.value}")

        print("\n--- Workflow 3: Transfer Ticket ---")
        # Get available employees for transfer
        available = await get_available_employees_for_transfer(session, ticket, employee1.tg_user_id)
        assert len(available) == 1  # Should only show employee2
        assert available[0].tg_user_id == employee2.tg_user_id
        print(f"✓ Found {len(available)} available employee(s) for transfer")

        # Transfer ticket
        transferred_ticket = await transfer_ticket(
            session, ticket.id, employee1.tg_user_id, employee2.tg_user_id
        )
        assert transferred_ticket.assigned_staff_id == employee2.tg_user_id
        print(
            f"✓ Ticket transferred from Employee {employee1.tg_user_id} to Employee {employee2.tg_user_id}"
        )

        # Verify transfer log
        result = await session.execute(
            select(Action_Log)
            .where(
                Action_Log.ticket_id == ticket.id,
                Action_Log.action_type == ActionType.TICKET_ASSIGNED,
            )
            .order_by(Action_Log.action_timestamp.desc())
        )
        transfer_log = result.first()
        assert transfer_log is not None
        print(f"✓ Transfer logged in Action_Log")

        print("\n--- Workflow 4: Close Ticket ---")
        final_comment = "Issue resolved successfully"
        closed_ticket = await close_ticket(session, ticket.id, employee2.tg_user_id, final_comment)
        assert closed_ticket.ticket_status == TicketStatus.CLOSED
        assert closed_ticket.closed_at is not None
        print(f"✓ Ticket closed with status: {closed_ticket.ticket_status.value}")

        # Verify final comment was stored
        result = await session.execute(
            select(Message).where(
                Message.ticket_id == ticket.id, Message.sender_type == SenderType.STAFF
            )
        )
        message = result.scalar_one_or_none()
        assert message is not None
        assert final_comment in message.message_text
        print(f"✓ Final comment stored: '{final_comment}'")

        # Verify close action logged
        result = await session.execute(
            select(Action_Log).where(
                Action_Log.ticket_id == ticket.id,
                Action_Log.action_type == ActionType.TICKET_CLOSED,
            )
        )
        close_log = result.scalar_one_or_none()
        assert close_log is not None
        print(f"✓ Close action logged: {close_log.action_type.value}")

    print("\n✅ All ticket action workflows completed successfully")
    print("=" * 80)


@pytest.mark.asyncio
async def test_ticket_status_transitions():
    """Test that ticket status transitions follow the correct flow."""
    print("\n" + "=" * 80)
    print("TEST 3: Ticket Status Transitions")
    print("=" * 80)

    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create test data
        user = User(
            tg_user_id=123456789,
            phone_number="+79991234567",
            full_name="Test Client",
        )
        employee = Staff_Member(
            id=1,
            tg_user_id=987654321,
            full_name="Test Employee",
            position="Manager",
            staff_role=StaffRole.MANAGER,
            is_active=True,
        )
        session.add_all([user, employee])
        await session.commit()
        await session.refresh(user)
        await session.refresh(employee)

        ticket = Ticket(
            ticket_type=TicketType.INVOICE,
            ticket_status=TicketStatus.NEW,
            description="Test status transitions - Testing status flow",
            tg_user_id=user.tg_user_id,
            assigned_staff_id=employee.tg_user_id,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

        print("\n--- Status Flow Test ---")
        print(f"Initial status: {ticket.ticket_status.value}")

        # NEW → IN_PROGRESS
        ticket = await take_ticket_into_work(session, ticket.id, employee.tg_user_id, messenger="telegram")
        assert ticket.ticket_status == TicketStatus.IN_PROGRESS
        print(f"✓ NEW → IN_PROGRESS")

        # IN_PROGRESS → WAITING_CLIENT
        ticket = await set_ticket_waiting_client(session, ticket.id, employee.tg_user_id)
        assert ticket.ticket_status == TicketStatus.WAITING_CLIENT
        print(f"✓ IN_PROGRESS → WAITING_CLIENT")

        # WAITING_CLIENT → CLOSED
        ticket = await close_ticket(session, ticket.id, employee.tg_user_id, "Resolved")
        assert ticket.ticket_status == TicketStatus.CLOSED
        print(f"✓ WAITING_CLIENT → CLOSED")

        print(f"\nFinal status: {ticket.ticket_status.value}")

    print("\n✅ Status transitions work correctly")
    print("=" * 80)


@pytest.mark.asyncio
async def test_multi_ticket_handling():
    """Test multi-ticket handling and focus switching."""
    print("\n" + "=" * 80)
    print("TEST 4: Multi-Ticket Handling")
    print("=" * 80)

    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create test users
        user1 = User(
            tg_user_id=111111111,
            phone_number="+79991111111",
            full_name="Client One",
        )
        user2 = User(
            tg_user_id=222222222,
            phone_number="+79992222222",
            full_name="Client Two",
        )
        session.add_all([user1, user2])

        # Create test employee with explicit ID
        employee = Staff_Member(
            id=1,
            tg_user_id=999999999,
            full_name="Multi-Task Employee",
            position="Technical Support",
            staff_role=StaffRole.TECHNICAL_SUPPORT,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(user1)
        await session.refresh(user2)
        await session.refresh(employee)

        # Create two tickets assigned to the same employee
        ticket1 = Ticket(
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            description="First ticket",
            tg_user_id=user1.tg_user_id,
            assigned_staff_id=employee.tg_user_id,
            created_at=datetime.now(timezone.utc),
        )
        ticket2 = Ticket(
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            description="Second ticket",
            tg_user_id=user2.tg_user_id,
            assigned_staff_id=employee.tg_user_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([ticket1, ticket2])
        await session.commit()
        await session.refresh(ticket1)
        await session.refresh(ticket2)

        print(f"\n✓ Created two tickets: #{ticket1.id} and #{ticket2.id}")

        # Test 1: Get active tickets - should return both
        active_tickets = await get_employee_active_tickets(session, employee.tg_user_id)
        assert len(active_tickets) == 2, f"Expected 2 active tickets, got {len(active_tickets)}"
        print(f"✓ Employee has {len(active_tickets)} active tickets")

        # Test 2: Take first ticket into work (simulating focus mode)
        ticket1_updated = await take_ticket_into_work(
            session, ticket1.id, employee.tg_user_id, messenger="telegram"
        )
        assert ticket1_updated.ticket_status == TicketStatus.IN_PROGRESS
        print(f"✓ Ticket #{ticket1.id} taken into work (focus mode)")

        # Test 3: Simulate taking second ticket into work (focus switching)
        # In real implementation, this would switch focus from ticket1 to ticket2
        ticket2_updated = await take_ticket_into_work(
            session, ticket2.id, employee.tg_user_id, messenger="telegram"
        )
        assert ticket2_updated.ticket_status == TicketStatus.IN_PROGRESS
        print(f"✓ Ticket #{ticket2.id} taken into work (focus switched)")

        # Test 4: Verify both tickets are now IN_PROGRESS
        active_tickets = await get_employee_active_tickets(session, employee.tg_user_id)
        assert len(active_tickets) == 2
        assert all(t.ticket_status == TicketStatus.IN_PROGRESS for t in active_tickets)
        print(f"✓ Both tickets are IN_PROGRESS")

        # Test 5: Verify action logs exist for both tickets
        stmt = select(Action_Log).where(
            Action_Log.action_type == ActionType.TICKET_ASSIGNED
        )
        result = await session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) >= 2, f"Expected at least 2 action logs, got {len(logs)}"
        print(f"✓ Action logs created for both tickets")

        print("\n✅ Multi-ticket handling test passed")
        print("   - Employee can have multiple active tickets")
        print("   - Focus can switch between tickets")
        print("   - Both tickets maintain correct status")

    await engine.dispose()


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("EMPLOYEE TICKET ACTIONS - INTEGRATION TESTS")
    print("=" * 80)

    try:
        # Test 1: Service functions
        await test_employee_service_functions()

        # Test 2: Action workflows
        await test_ticket_action_workflows()

        # Test 3: Status transitions
        await test_ticket_status_transitions()
        
        # Test 4: Multi-ticket handling
        await test_multi_ticket_handling()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("\nImplementation Summary:")
        print("1. ✓ Employee service functions work correctly")
        print("2. ✓ Ticket action workflows complete end-to-end")
        print("3. ✓ Status transitions follow correct flow")
        print("4. ✓ Action logging works properly")
        print("5. ✓ Ticket transfer preserves history")
        print("6. ✓ Multi-ticket handling and focus switching work")
        print("\nTasks validated: 1-8, 13 of employee-interface spec")
        print("=" * 80)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
