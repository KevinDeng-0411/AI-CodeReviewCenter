"""认证契约（团队化升级阶段 A）。"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="member", pattern="^(admin|member)$")
    display_name: str | None = Field(default=None, max_length=100)


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    display_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
