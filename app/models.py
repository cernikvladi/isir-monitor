from sqlalchemy import BigInteger, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    spisova_znacka: Mapped[str | None] = mapped_column(Text, nullable=True)
    typ_udalosti: Mapped[int | None] = mapped_column(Integer, nullable=True)
    popis_udalosti: Mapped[str | None] = mapped_column(Text, nullable=True)
    datum_zverejneni: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dokument_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_xml: Mapped[str | None] = mapped_column(Text, nullable=True)