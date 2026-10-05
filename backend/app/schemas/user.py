"""Outbound user representations. None of them can carry the password hash."""
from pydantic import BaseModel, ConfigDict


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    kind: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    department: DepartmentOut | None
    authority_level: int | None
    is_active: bool


class CurrentUserOut(UserOut):
    # Copy of the server-side role permissions, for the UI only.
    permissions: list[str]
