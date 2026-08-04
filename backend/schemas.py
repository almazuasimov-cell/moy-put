"""Pydantic schemas for request/response validation."""
from typing import Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    phone: str
    name: str
    password: str
    consent: bool = False


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    plan: str = "free"
    balance: int = 0


class DiaryEntryCreate(BaseModel):
    transcript_text: str
    structured_text: str = ""
    mood: int = 5
    tags: list = []
    topics: list = []
    ai_summary: str = ""
    reflection: str = ""


class ProcessRequest(BaseModel):
    text: str


class ProcessResponse(BaseModel):
    mood: int
    tags: list
    topics: list
    structured_text: str
    ai_summary: str
    reflection: str


class SearchRequest(BaseModel):
    query: str


class BiographyUpdate(BaseModel):
    content: str


class SubscriptionInfo(BaseModel):
    plan: str
    status: str
    voice_entries_used: int
    voice_entries_limit: int
    biography_generations_used: int
    biography_generations_limit: int
    ai_searches_used: int
    ai_searches_limit: int
    expires_at: Optional[str] = None


class ReferralApplyRequest(BaseModel):
    code: str


class ReferralInfo(BaseModel):
    code: str
    balance: int
    invited_count: int
    referrals: list = []
