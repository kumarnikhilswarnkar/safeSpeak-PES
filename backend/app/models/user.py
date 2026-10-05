from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import AUTHORITY_ROLES, DEPARTMENT_REQUIRED_ROLES, Role
from app.db.base import Base, TimestampMixin
from app.models.department import Department


def _sql_list(values) -> str:
    return ", ".join(f"'{v.value}'" for v in sorted(values))


class User(TimestampMixin, Base):
    __tablename__ = "users"
    # The database enforces the same account rules as the service layer, so an
    # invalid account cannot be created even by a script that bypasses the API.
    __table_args__ = (
        CheckConstraint(f"role IN ({_sql_list(Role)})", name="role_valid"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # IS NOT NULL is required: "NULL >= 1" is NULL, and a CHECK passes on NULL.
        CheckConstraint(
            f"(role IN ({_sql_list(AUTHORITY_ROLES)}) AND authority_level IS NOT NULL AND authority_level >= 1)"
            f" OR (role NOT IN ({_sql_list(AUTHORITY_ROLES)}) AND authority_level IS NULL)",
            name="authority_level_matches_role",
        ),
        CheckConstraint(
            f"role NOT IN ({_sql_list(DEPARTMENT_REQUIRED_ROLES)}) OR department_id IS NOT NULL",
            name="department_required_for_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32), index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    authority_level: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    department: Mapped[Department | None] = relationship()

    def __repr__(self) -> str:  # never include the password hash
        return f"<User id={self.id} role={self.role} email={self.email}>"
