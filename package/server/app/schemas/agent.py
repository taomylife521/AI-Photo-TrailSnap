from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

# ---- Agent Message Schemas ----

class AgentMessageBase(BaseModel):
    role: str = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., description="Message content")
    content_type: str = Field(default="text", description="Content type (text/image/etc)")
    content_ext: Optional[Dict[str, Any]] = Field(default=None, description="Extended content data")
    reasoning: Optional[str] = Field(default=None, description="Reasoning text")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool calls list")
    token_count: int = Field(default=0, description="Number of tokens used")

class AgentMessageCreate(AgentMessageBase):
    session_id: UUID

class AgentMessage(AgentMessageBase):
    id: int
    session_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# ---- Agent Session Schemas ----

class AgentSessionBase(BaseModel):
    title: Optional[str] = Field(default=None, description="Session title")
    status: str = Field(default="active", description="Session status (active/closed/etc)")
    context_summary: Optional[str] = Field(default=None, description="Summary of session context")
    is_pinned: bool = Field(default=False, description="Whether session is pinned")

class AgentSessionCreate(AgentSessionBase):
    id: Optional[UUID] = Field(default=None, description="Session ID")

class AgentSessionUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    context_summary: Optional[str] = None
    summary_update_time: Optional[datetime] = None
    is_pinned: Optional[bool] = None

class AgentSession(AgentSessionBase):
    id: UUID
    user_id: UUID
    summary_update_time: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AgentSessionWithMessages(AgentSession):
    messages: List[AgentMessage] = []
