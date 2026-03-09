"""
Escalation Test API Schemas

Pydantic schemas for testing escalation functionality via API.
"""

from pydantic import BaseModel, Field


class EscalationTestRequest(BaseModel):
    """Request schema for testing ticket escalation."""
    
    ticket_id: int = Field(..., description="ID of the ticket to test escalation for")
    force_escalation: bool = Field(
        default=False,
        description="If True, forces escalation even if ticket is not in NEW status"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticket_id": 123,
                "force_escalation": False
            }
        }


class EscalationTestResponse(BaseModel):
    """Response schema for escalation test."""
    
    success: bool = Field(..., description="Whether the test was successful")
    message: str = Field(..., description="Human-readable message about the result")
    ticket_id: int = Field(..., description="ID of the tested ticket")
    escalation_triggered: bool = Field(..., description="Whether escalation was triggered")
    escalation_id: int | None = Field(None, description="ID of created escalation (if any)")
    current_status: str = Field(..., description="Current ticket status")
    assigned_staff_id: int | None = Field(None, description="Currently assigned staff ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Escalation test completed successfully",
                "ticket_id": 123,
                "escalation_triggered": True,
                "escalation_id": 45,
                "current_status": "new",
                "assigned_staff_id": 789
            }
        }


class BackupManagerTestRequest(BaseModel):
    """Request schema for testing backup manager reassignment."""
    
    ticket_id: int = Field(..., description="ID of the ticket to test backup manager reassignment")
    target_backup_slot: int | None = Field(
        None,
        description="Which backup manager to test (1 or 2). If None, tests both in sequence."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticket_id": 123,
                "target_backup_slot": 1
            }
        }


class BackupManagerTestResponse(BaseModel):
    """Response schema for backup manager test."""
    
    success: bool = Field(..., description="Whether the test was successful")
    message: str = Field(..., description="Human-readable message about the result")
    ticket_id: int = Field(..., description="ID of the tested ticket")
    original_staff_id: int | None = Field(None, description="Original assigned staff ID")
    original_staff_name: str | None = Field(None, description="Original assigned staff name")
    backup_1_id: int | None = Field(None, description="Backup manager 1 ID")
    backup_1_name: str | None = Field(None, description="Backup manager 1 name")
    backup_2_id: int | None = Field(None, description="Backup manager 2 ID")
    backup_2_name: str | None = Field(None, description="Backup manager 2 name")
    reassigned_to_id: int | None = Field(None, description="Staff ID ticket was reassigned to")
    reassigned_to_name: str | None = Field(None, description="Staff name ticket was reassigned to")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Ticket successfully reassigned to backup manager 1",
                "ticket_id": 123,
                "original_staff_id": 789,
                "original_staff_name": "Иван Иванов",
                "backup_1_id": 456,
                "backup_1_name": "Петр Петров",
                "backup_2_id": 321,
                "backup_2_name": "Сидор Сидоров",
                "reassigned_to_id": 456,
                "reassigned_to_name": "Петр Петров"
            }
        }
