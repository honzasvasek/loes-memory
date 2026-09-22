from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class MemoryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    type: Literal['profile', 'episodic']
    text: str = Field(min_length=1, max_length=1000)
    importance: float = Field(.5, ge=0, le=1)
    confidence: float = Field(1, ge=0, le=1)


class ImportanceUpdate(BaseModel):
    importance: float = Field(ge=0, le=1)


class RecallInput(BaseModel):
    message: str = Field(min_length=1, max_length=30000)


class Observation(BaseModel):
    user: str = Field(min_length=1, max_length=30000)
    assistant: str = Field(min_length=1, max_length=100000)
    observation_id: str | None = Field(None, max_length=200)


class Extraction(BaseModel):
    memories: list[MemoryInput] = Field(max_length=8)
