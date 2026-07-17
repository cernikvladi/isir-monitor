from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Event(Base):
    """Append-only log of every akce/podnet returned by getIsirWsPublicPodnetId.

    This is the source of truth: the normalized tables below are just a
    materialized, upsertable view built by replaying these events.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    datum_zalozeni_udalosti: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    datum_zverejneni_udalosti: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spisova_znacka: Mapped[str | None] = mapped_column(String(50), index=True)
    typ_udalosti: Mapped[str | None] = mapped_column(String(20))
    popis_udalosti: Mapped[str | None] = mapped_column(Text)
    oddil: Mapped[str | None] = mapped_column(String(10))
    cislo_v_oddilu: Mapped[int | None] = mapped_column(Integer)
    dokument_url: Mapped[str | None] = mapped_column(Text)
    poznamka_xml: Mapped[str | None] = mapped_column(Text)
    poznamka: Mapped[dict | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncState(Base):
    """Singleton row tracking how far the incremental poller has gotten."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_processed_id: Mapped[int] = mapped_column(BigInteger, default=-1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Case(Base):
    """Current normalized state of an insolvency case (věc), keyed by spisová značka."""

    __tablename__ = "cases"

    spisova_znacka: Mapped[str] = mapped_column(String(50), primary_key=True)
    druh_stav_rizeni: Mapped[str | None] = mapped_column(String(20))
    datum_konec_lhuty_prihlasek: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    datum_skonceni_veci: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    datum_vec_zrusena: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mezinarodni_prislus_soudu: Mapped[str | None] = mapped_column(Text)
    last_event_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Person(Base):
    """Current normalized state of a person/entity involved in a case.

    idOsoby is only unique within the originating court (idOsobyPuvodce), so
    the natural key combines both, per the WS_1 docs (1.4.2 Založení osoby v řízení).
    """

    __tablename__ = "persons"
    __table_args__ = (
        UniqueConstraint("spisova_znacka", "id_osoby_puvodce", "id_osoby", name="uq_person_key"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spisova_znacka: Mapped[str] = mapped_column(
        String(50), ForeignKey("cases.spisova_znacka"), index=True
    )
    id_osoby_puvodce: Mapped[str | None] = mapped_column(String(20))
    id_osoby: Mapped[str | None] = mapped_column(String(20))
    druh_role_v_rizeni: Mapped[str | None] = mapped_column(String(20))
    nazev_osoby: Mapped[str | None] = mapped_column(String(255), index=True)
    nazev_osoby_obchodni: Mapped[str | None] = mapped_column(String(255))
    druh_osoby: Mapped[str | None] = mapped_column(String(20))
    druh_pravni_forma: Mapped[str | None] = mapped_column(String(20))
    jmeno: Mapped[str | None] = mapped_column(String(80))
    titul_pred: Mapped[str | None] = mapped_column(String(50))
    titul_za: Mapped[str | None] = mapped_column(String(50))
    ic: Mapped[str | None] = mapped_column(String(9), index=True)
    dic: Mapped[str | None] = mapped_column(String(14))
    rc: Mapped[str | None] = mapped_column(String(11), index=True)
    datum_narozeni: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    datum_osoba_ve_veci_zrusena: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Address(Base):
    """Current normalized address of a person, keyed by (person, druh_adresy).

    A person can carry several address types (TRVALÁ, SÍDLO FY, ...)
    simultaneously; each type is upserted independently as updates arrive.
    """

    __tablename__ = "addresses"
    __table_args__ = (
        UniqueConstraint(
            "spisova_znacka", "id_osoby_puvodce", "id_osoby", "druh_adresy", name="uq_address_key"
        ),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spisova_znacka: Mapped[str] = mapped_column(String(50), index=True)
    id_osoby_puvodce: Mapped[str | None] = mapped_column(String(20))
    id_osoby: Mapped[str | None] = mapped_column(String(20))
    druh_adresy: Mapped[str | None] = mapped_column(String(20))
    id_adresy: Mapped[str | None] = mapped_column(String(20))
    datum_pobyt_od: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    datum_pobyt_do: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mesto: Mapped[str | None] = mapped_column(String(255))
    ulice: Mapped[str | None] = mapped_column(String(255))
    cislo_popisne: Mapped[str | None] = mapped_column(String(10))
    okres: Mapped[str | None] = mapped_column(String(30))
    zeme: Mapped[str | None] = mapped_column(String(255))
    psc: Mapped[str | None] = mapped_column(String(6))
    telefon: Mapped[str | None] = mapped_column(String(30))
    fax: Mapped[str | None] = mapped_column(String(30))
    text_adresy: Mapped[str | None] = mapped_column(String(255))
    last_event_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
