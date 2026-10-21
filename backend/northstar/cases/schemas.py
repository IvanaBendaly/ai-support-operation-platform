"""Validated inputs shared by HTTP endpoints and trusted internal callers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["general", "billing", "account", "technical", "privacy"]
Status = Literal["open", "processing", "awaiting_customer", "escalated", "resolved", "failed"]
Disposition = Literal[
    "answered", "action_completed", "clarification_requested", "refused", "escalated"
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Context(Input):
    invoice_id: str | None = Field(default=None, min_length=1, max_length=36)
    client_reference: str | None = Field(default=None, min_length=1, max_length=100)


class CreateCase(Input):
    account_id: str = Field(min_length=1, max_length=36)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    category: Category = "general"
    context: Context = Field(default_factory=Context)


class FollowUp(Input):
    message: str = Field(min_length=1, max_length=8000)
    expected_version: int = Field(ge=1, strict=True)


class Outcome(Input):
    disposition: Disposition
    reply: str = Field(min_length=1, max_length=8000)
    action_id: str | None = Field(default=None, min_length=1, max_length=100)
    decision_id: str | None = Field(default=None, min_length=1, max_length=100)
    escalation_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def action_reference(self):
        if self.disposition == "action_completed" and not self.action_id:
            raise ValueError("action_completed requires an action_id")
        return self


class HumanOutcome(Outcome):
    expected_version: int = Field(ge=1, strict=True)


class Retry(Input):
    expected_version: int = Field(ge=1, strict=True)
