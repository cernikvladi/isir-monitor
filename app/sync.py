"""Ingestion pipeline for ISIR_PUBLIC_WS events.

Two entry points matter to callers:
- bootstrap(session): one-time setup, moves the cursor back to the backfill
  cutoff (via binary search) and then drains forward to the present.
- run_sync_cycle(session): the steady-state poller, drains whatever's newly
  available from the cursor forward. Safe to call repeatedly/idempotently.

Both operate on the same append-only `events` log plus the normalized
Case/Person/Address tables, which are upserted with COALESCE-based merges so
a later event that omits a field never clobbers a value set by an earlier one.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.isir_client import BATCH_SIZE, get_events, get_last_podnet_id
from app.models import Address, Case, Event, Person, SyncState
from app.poznamka import parse_isir_date, parse_poznamka

# BACKFILL_SINCE (e.g. "2025-01-01") pins an absolute cutoff date and takes
# precedence when set. BACKFILL_YEARS is the fallback: a rolling window
# relative to now, for deployments that don't want to hardcode a date.
BACKFILL_SINCE = os.getenv("BACKFILL_SINCE")
BACKFILL_YEARS = int(os.getenv("BACKFILL_YEARS", "3"))
SYNC_STATE_ID = 1


def _backfill_cutoff() -> datetime:
    if BACKFILL_SINCE:
        return datetime.fromisoformat(BACKFILL_SINCE).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - timedelta(days=365 * BACKFILL_YEARS)


def _get_or_create_sync_state(session: Session) -> SyncState:
    state = session.get(SyncState, SYNC_STATE_ID)
    if state is None:
        state = SyncState(id=SYNC_STATE_ID, last_processed_id=-1)
        session.add(state)
        session.flush()
    return state


def find_backfill_start_id(cutoff: datetime, last_id: int) -> int:
    """Binary search for the largest event id whose datumZalozeniUdalosti < cutoff.

    IDs are generated sequentially by the central system as events are
    recorded (Popis_WS_1 1.2.2), so id order closely tracks time order - a
    good enough proxy for a bounded-backfill starting point without needing
    to walk the full history just to find it.
    """
    lo, hi = -1, last_id
    while lo < hi:
        mid = (lo + hi + 1) // 2
        probe = get_events(mid - 1)
        if not probe:
            hi = mid - 1
            continue
        probe_date = probe[0]["datum_zalozeni_udalosti"]
        if probe_date and probe_date >= cutoff:
            hi = mid - 1
        else:
            lo = mid
    return lo


def _coalesce_set(stmt, model, columns: list[str]) -> dict:
    """Build an ON CONFLICT DO UPDATE set_ clause that keeps existing values
    for any column the new event didn't provide, instead of nulling them out."""
    update = {
        col: func.coalesce(getattr(stmt.excluded, col), getattr(model, col)) for col in columns
    }
    update["last_event_id"] = stmt.excluded.last_event_id
    update["updated_at"] = func.now()
    return update


def _upsert_event(session: Session, event: dict, poznamka: dict | None) -> None:
    stmt = pg_insert(Event).values(
        id=event["id"],
        datum_zalozeni_udalosti=event["datum_zalozeni_udalosti"],
        datum_zverejneni_udalosti=event["datum_zverejneni_udalosti"],
        spisova_znacka=event["spisova_znacka"],
        typ_udalosti=event["typ_udalosti"],
        popis_udalosti=event["popis_udalosti"],
        oddil=event["oddil"],
        cislo_v_oddilu=event["cislo_v_oddilu"],
        dokument_url=event["dokument_url"],
        poznamka_xml=event["poznamka_xml"],
        poznamka=poznamka,
    ).on_conflict_do_nothing(index_elements=["id"])
    session.execute(stmt)


def _upsert_case(session: Session, spisova_znacka: str, vec: dict | None, event_id: int) -> None:
    vec = vec or {}
    stmt = pg_insert(Case).values(
        spisova_znacka=spisova_znacka,
        druh_stav_rizeni=vec.get("druhStavRizeni"),
        datum_konec_lhuty_prihlasek=parse_isir_date(vec.get("datumKonecLhutyPrihlasek")),
        datum_skonceni_veci=parse_isir_date(vec.get("datumSkonceniVeci")),
        datum_vec_zrusena=parse_isir_date(vec.get("datumVecZrusena")),
        mezinarodni_prislus_soudu=vec.get("mezinarodniPrislusSoudu"),
        last_event_id=event_id,
    )
    cols = [
        "druh_stav_rizeni",
        "datum_konec_lhuty_prihlasek",
        "datum_skonceni_veci",
        "datum_vec_zrusena",
        "mezinarodni_prislus_soudu",
    ]
    stmt = stmt.on_conflict_do_update(
        index_elements=["spisova_znacka"], set_=_coalesce_set(stmt, Case, cols)
    )
    session.execute(stmt)


def _upsert_person(
    session: Session,
    spisova_znacka: str,
    id_osoby_puvodce: str | None,
    osoba: dict,
    event_id: int,
) -> None:
    id_osoby = osoba.get("idOsoby")
    if not id_osoby:
        return
    stmt = pg_insert(Person).values(
        spisova_znacka=spisova_znacka,
        id_osoby_puvodce=id_osoby_puvodce,
        id_osoby=id_osoby,
        druh_role_v_rizeni=osoba.get("druhRoleVRizeni"),
        nazev_osoby=osoba.get("nazevOsoby"),
        nazev_osoby_obchodni=osoba.get("nazevOsobyObchodni"),
        druh_osoby=osoba.get("druhOsoby"),
        druh_pravni_forma=osoba.get("druhPravniForma"),
        jmeno=osoba.get("jmeno"),
        titul_pred=osoba.get("titulPred"),
        titul_za=osoba.get("titulZa"),
        ic=osoba.get("ic"),
        dic=osoba.get("dic"),
        rc=osoba.get("rc"),
        datum_narozeni=parse_isir_date(osoba.get("datumNarozeni")),
        datum_osoba_ve_veci_zrusena=parse_isir_date(osoba.get("datumOsobaVeVeciZrusena")),
        last_event_id=event_id,
    )
    cols = [
        "druh_role_v_rizeni",
        "nazev_osoby",
        "nazev_osoby_obchodni",
        "druh_osoby",
        "druh_pravni_forma",
        "jmeno",
        "titul_pred",
        "titul_za",
        "ic",
        "dic",
        "rc",
        "datum_narozeni",
        "datum_osoba_ve_veci_zrusena",
    ]
    stmt = stmt.on_conflict_do_update(
        index_elements=["spisova_znacka", "id_osoby_puvodce", "id_osoby"],
        set_=_coalesce_set(stmt, Person, cols),
    )
    session.execute(stmt)

    adresa = osoba.get("adresa")
    if isinstance(adresa, dict) and adresa.get("druhAdresy"):
        _upsert_address(session, spisova_znacka, id_osoby_puvodce, id_osoby, adresa, event_id)


def _upsert_address(
    session: Session,
    spisova_znacka: str,
    id_osoby_puvodce: str | None,
    id_osoby: str,
    adresa: dict,
    event_id: int,
) -> None:
    stmt = pg_insert(Address).values(
        spisova_znacka=spisova_znacka,
        id_osoby_puvodce=id_osoby_puvodce,
        id_osoby=id_osoby,
        druh_adresy=adresa.get("druhAdresy"),
        id_adresy=adresa.get("idAdresy"),
        datum_pobyt_od=parse_isir_date(adresa.get("datumPobytOd")),
        datum_pobyt_do=parse_isir_date(adresa.get("datumPobytDo")),
        mesto=adresa.get("mesto"),
        ulice=adresa.get("ulice"),
        cislo_popisne=adresa.get("cisloPopisne"),
        okres=adresa.get("okres"),
        zeme=adresa.get("zeme"),
        psc=adresa.get("psc"),
        telefon=adresa.get("telefon"),
        fax=adresa.get("fax"),
        text_adresy=adresa.get("textAdresy"),
        last_event_id=event_id,
    )
    cols = [
        "id_adresy",
        "datum_pobyt_od",
        "datum_pobyt_do",
        "mesto",
        "ulice",
        "cislo_popisne",
        "okres",
        "zeme",
        "psc",
        "telefon",
        "fax",
        "text_adresy",
    ]
    stmt = stmt.on_conflict_do_update(
        index_elements=["spisova_znacka", "id_osoby_puvodce", "id_osoby", "druh_adresy"],
        set_=_coalesce_set(stmt, Address, cols),
    )
    session.execute(stmt)


def ingest_batch(session: Session, events: list[dict]) -> int:
    """Upsert a batch of raw events plus the case/person/address state they imply.

    Returns the highest event id processed (-1 if events was empty).
    """
    max_id = -1
    for event in events:
        poznamka = parse_poznamka(event["poznamka_xml"])
        _upsert_event(session, event, poznamka)

        spisova_znacka = event["spisova_znacka"]
        if spisova_znacka:
            id_osoby_puvodce = (poznamka or {}).get("idOsobyPuvodce")
            # Case row must exist before Person/Address (FK), so upsert it
            # unconditionally even when this event carries no `vec` data.
            _upsert_case(session, spisova_znacka, (poznamka or {}).get("vec"), event["id"])

            osoba = (poznamka or {}).get("osoba")
            osoby = osoba if isinstance(osoba, list) else [osoba] if osoba else []
            for item in osoby:
                if isinstance(item, dict):
                    _upsert_person(session, spisova_znacka, id_osoby_puvodce, item, event["id"])

        max_id = max(max_id, event["id"])
    session.commit()
    return max_id


def run_sync_cycle(session: Session, max_batches: int | None = 20) -> int:
    """Drain events from the cursor forward until caught up (or max_batches hit).

    max_batches bounds worst-case runtime for periodic scheduler ticks; pass
    None for an unbounded drain (used by bootstrap's initial catch-up).
    """
    state = _get_or_create_sync_state(session)
    total = 0
    batches = 0
    while max_batches is None or batches < max_batches:
        events = get_events(state.last_processed_id)
        batches += 1
        if not events:
            break
        max_id = ingest_batch(session, events)
        state.last_processed_id = max_id
        session.commit()
        total += len(events)
        if len(events) < BATCH_SIZE:
            break
    return total


def bootstrap(session: Session) -> int:
    """One-time setup: point the cursor at the backfill cutoff, then drain to present.

    Idempotent - if the cursor has already been moved past -1 (by a previous
    bootstrap call), this just behaves like an unbounded run_sync_cycle.
    """
    state = _get_or_create_sync_state(session)
    if state.last_processed_id <= -1:
        last_id = get_last_podnet_id()
        state.last_processed_id = find_backfill_start_id(_backfill_cutoff(), last_id)
        session.commit()
    return run_sync_cycle(session, max_batches=None)
