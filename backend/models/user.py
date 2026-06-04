"""
User model for authentication and user management.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
import uuid


class User(BaseModel):
    """User model with authentication fields"""
    username: str  # This is the user_id / primary key
    email: EmailStr
    password_hash: Optional[str] = None  # None for OAuth users
    full_name: Optional[str] = None
    oauth_provider: Optional[str] = None  # 'google', 'github', etc.
    oauth_id: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_login: Optional[str] = None
    profile_picture: Optional[str] = None


class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user data response"""
    username: str  # user_id
    email: str
    full_name: Optional[str]
    profile_picture: Optional[str]
    created_at: str


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Data stored in JWT token"""
    username: str  # user_id
    email: str
