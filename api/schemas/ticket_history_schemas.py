"""
Pydantic schemas for ticket history API endpoint.

This module defines response schemas for the ticket history API endpoint
that returns complete ticket history including messages, status changes, and assignments.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MessageDTO(BaseModel):
    """
    Data transfer object for ticket message.
    
    Attributes:
        message_id: Unique message identifier
        sender_type: Type of sender ("user" or "staff")
        sender_id: ID of sender (user_id or staff_id)
        sender_name: Display name of sender
        message_text: Message content
        created_at: Message timestamp
        attachments: List of file attachment URLs
    """
    
    message_id: int = Field(..., description="Unique message identifier")
    sender_type: str = Field(..., description="Type of sender (user or staff)")
    sender_id: int = Field(..., description="ID of sender")
    sender_name: str = Field(..., description="Display name of sender")
    message_text: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="Message timestamp")
    attachments: list[str] = Field(default_factory=list, description="List of file attachment URLs")


class StatusChangeDTO(BaseModel):
    """
    Data transfer object for ticket status change.
    
    Attributes:
        change_id: Unique change identifier
        old_status: Previous ticket status
        new_status: New ticket status
        changed_by_staff_id: Staff member who made the change
        changed_by_staff_name: Display name of staff member
        changed_at: Change timestamp
        reason: Optional reason for status change
    """
    
    change_id: int = Field(..., description="Unique change identifier")
    old_status: str = Field(..., description="Previous ticket status")
    new_status: str = Field(..., description="New ticket status")
    changed_by_staff_id: int = Field(..., description="Staff member who made the change")
    changed_by_staff_name: str = Field(..., description="Display name of staff member")
    changed_at: datetime = Field(..., description="Change timestamp")
    reason: str | None = Field(None, description="Optional reason for status change")


class AssignmentDTO(BaseModel):
    """
    Data transfer object for ticket assignment.
    
    Attributes:
        assignment_id: Unique assignment identifier
        assigned_to_staff_id: Staff member assigned to ticket
        assigned_to_staff_name: Display name of staff member
        assigned_by_staff_id: Staff member who made the assignment (if applicable)
        assigned_by_staff_name: Display name of assigning staff member
        assigned_at: Assignment timestamp
        assignment_type: Type of assignment ("initial", "reassignment", "escalation")
        reason: Optional reason for assignment
    """
    
    assignment_id: int = Field(..., description="Unique assignment identifier")
    assigned_to_staff_id: int = Field(..., description="Staff member assigned to ticket")
    assigned_to_staff_name: str = Field(..., description="Display name of staff member")
    assigned_by_staff_id: int | None = Field(None, description="Staff member who made the assignment")
    assigned_by_staff_name: str | None = Field(None, description="Display name of assigning staff member")
    assigned_at: datetime = Field(..., description="Assignment timestamp")
    assignment_type: str = Field(..., description="Type of assignment")
    reason: str | None = Field(None, description="Optional reason for assignment")


class TicketHistoryResponse(BaseModel):
    """
    Response for ticket history API endpoint.
    
    Attributes:
        ticket_id: Unique ticket identifier
        ticket_type: Type of ticket ("support" or "invoice")
        current_status: Current ticket status
        created_at: Ticket creation timestamp
        updated_at: Last update timestamp
        closed_at: Ticket closure timestamp (if closed)
        messages: List of all messages in chronological order
        status_changes: List of all status changes in chronological order
        assignments: List of all staff assignments in chronological order
    """
    
    ticket_id: str = Field(..., description="Unique ticket identifier")
    ticket_type: str = Field(..., description="Type of ticket")
    current_status: str = Field(..., description="Current ticket status")
    created_at: datetime = Field(..., description="Ticket creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    closed_at: datetime | None = Field(None, description="Ticket closure timestamp")
    messages: list[MessageDTO] = Field(default_factory=list, description="All messages in chronological order")
    status_changes: list[StatusChangeDTO] = Field(default_factory=list, description="All status changes")
    assignments: list[AssignmentDTO] = Field(default_factory=list, description="All staff assignments")
