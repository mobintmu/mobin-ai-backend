import uuid
from datetime import datetime
from typing import Literal

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class RegisterIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "given_name": "Ada",
                    "family_name": "Lovelace",
                    "email": "ada@example.com",
                    "privacy_accepted": True,
                    "privacy_policy_version": "2026-09-25",
                    "marketing_consent": False,
                    "turnstile_token": "turnstile-response",
                }
            ]
        }
    )
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = None
    privacy_accepted: bool
    privacy_policy_version: str = Field(min_length=1, max_length=40)
    marketing_consent: bool = False
    turnstile_token: str = Field(min_length=1, max_length=2048)

    @field_validator("given_name", "family_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("Phone must include a country code") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    @model_validator(mode="after")
    def require_contact_and_consent(self) -> "RegisterIn":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        if not self.privacy_accepted:
            raise ValueError("Privacy policy acceptance is required")
        return self


class RegisterOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "client_id": "01900000-0000-7000-8000-000000000000",
                    "registration_grant": "short-lived-one-time-grant",
                    "grant_expires_at": "2026-09-25T12:05:00Z",
                }
            ]
        }
    )
    client_id: uuid.UUID
    registration_grant: str
    grant_expires_at: datetime


class ConversationIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "client_id": "01900000-0000-7000-8000-000000000000",
                    "registration_grant": "one-time-grant-from-registration",
                }
            ]
        }
    )
    client_id: uuid.UUID
    registration_grant: str = Field(min_length=20)


class Quota(BaseModel):
    limit: int
    used: int
    remaining: int


class ConversationOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "conversation_id": "01900000-0000-7000-8000-000000000001",
                    "access_token": "opaque-random-token",
                    "expires_at": "2026-10-25T12:00:00Z",
                    "quota": {"limit": 100, "used": 0, "remaining": 100},
                }
            ]
        }
    )
    conversation_id: uuid.UUID
    access_token: str
    expires_at: datetime
    quota: Quota


class ConversationInfo(BaseModel):
    conversation_id: uuid.UUID
    expires_at: datetime
    quota: Quota


class QuestionIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"question": "How should a high-TPS Kafka to ClickHouse pipeline be designed?"}
            ]
        }
    )
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question is required")
        return value


class Citation(BaseModel):
    citation_id: str
    title: str
    url: str
    snippet: str
    source_type: Literal["article"] = "article"
    source_id: str | None = None
    score: float | None = None


class AnswerOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message_id": "01900000-0000-7000-8000-000000000002",
                    "conversation_id": "01900000-0000-7000-8000-000000000001",
                    "answer": "Use bounded batches. [c1]",
                    "grounded": True,
                    "citations": [
                        {
                            "citation_id": "c1",
                            "title": "Example article",
                            "url": "https://mobinshaterian.com/blog/example",
                            "snippet": "Relevant passage",
                            "source_type": "article",
                        }
                    ],
                    "quota": {"limit": 100, "used": 1, "remaining": 99},
                    "request_id": "01900000-0000-7000-8000-000000000003",
                }
            ]
        }
    )
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: str
    grounded: bool
    citations: list[Citation]
    quota: Quota
    request_id: uuid.UUID


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    status: str
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]
    next_cursor: datetime | None = None


class FeedbackIn(BaseModel):
    helpful: bool


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str
