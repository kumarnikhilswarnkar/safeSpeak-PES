from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DepartmentKind(StrEnum):
    ACADEMIC = "ACADEMIC"  # e.g. MCA, CSE
    OFFICE = "OFFICE"  # e.g. Hostel Office, Examination Cell


class Department(TimestampMixin, Base):
    """An academic department or an administrative office.

    Both kinds live in one table so routing can target either.
    """

    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ACADEMIC', 'OFFICE')",
            name="kind_valid",
        ),
        CheckConstraint("code = upper(code)", name="code_uppercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
