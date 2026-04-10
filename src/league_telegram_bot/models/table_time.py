from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .table import Table


class TableTime(Base):
    __tablename__ = "table_times"
    table_time_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"))
    time: Mapped[int] = mapped_column(insert_default=0)
    games: Mapped[int] = mapped_column(insert_default=4)
    need_reminder: Mapped[int] = mapped_column(insert_default=0)
    table: Mapped[Table] = relationship(back_populates="table_times", lazy="subquery")
