from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .models import UserRole

# ==================================================================
# Token Schemas
# ==================================================================
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# ==================================================================
# User & Organization Schemas
# ==================================================================
class OrganizationBase(BaseModel):
    name: str

class OrganizationCreate(OrganizationBase):
    pass

class Organization(OrganizationBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    role: UserRole = UserRole.MEMBER

class UserCreate(UserBase):
    password: str
    organization_id: int

class User(UserBase):
    id: int
    is_active: bool
    organization: Organization

    class Config:
        from_attributes = True 