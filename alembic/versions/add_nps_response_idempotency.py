"""Make NPS responses idempotent.

Revision ID: nps_response_idempotency
Revises: expand_escalation_lvl_3
Create Date: 2026-07-19
"""

from alembic import op

revision = "nps_response_idempotency"
down_revision = "expand_escalation_lvl_3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve one response and any available feedback before removing duplicates.
    op.execute(
        """
        WITH duplicate_groups AS (
            SELECT
                user_id,
                survey_type,
                trigger_event_id,
                MIN(id) AS keep_id,
                MIN(sent_at) AS sent_at,
                MIN(responded_at) AS responded_at,
                MAX(feedback_comment) FILTER (
                    WHERE feedback_comment IS NOT NULL
                ) AS feedback_comment
            FROM nps_responses
            GROUP BY user_id, survey_type, trigger_event_id
            HAVING COUNT(*) > 1
        )
        UPDATE nps_responses AS response
        SET
            sent_at = duplicate.sent_at,
            responded_at = duplicate.responded_at,
            feedback_comment = COALESCE(
                response.feedback_comment,
                duplicate.feedback_comment
            )
        FROM duplicate_groups AS duplicate
        WHERE response.id = duplicate.keep_id
        """
    )

    op.execute(
        """
        DELETE FROM nps_responses AS duplicate
        USING nps_responses AS keeper
        WHERE duplicate.user_id = keeper.user_id
          AND duplicate.survey_type = keeper.survey_type
          AND duplicate.trigger_event_id = keeper.trigger_event_id
          AND duplicate.id > keeper.id
        """
    )

    op.create_unique_constraint(
        "uq_nps_response_user_survey_trigger",
        "nps_responses",
        ["user_id", "survey_type", "trigger_event_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_nps_response_user_survey_trigger",
        "nps_responses",
        type_="unique",
    )
