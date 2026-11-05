"""Request of POST /api/chat (the contract with frontend/src/api.ts)."""
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    conversation: list[Turn] = Field(min_length=1, max_length=20)
    today: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="the visitor's 'today' (knowledge cutoff)")
    campus: Literal["zgc", "tz"] | None = None
    model: Literal["deepseek"] = "deepseek"
    compare: bool = True
    lang: Literal["en", "zh"] = "en"
