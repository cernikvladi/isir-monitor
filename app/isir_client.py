import logging
from functools import lru_cache

from zeep import Client
from zeep.exceptions import Fault

logger = logging.getLogger(__name__)

WSDL_URL = (
    "https://isir.justice.cz:8443/"
    "isir_public_ws/IsirWsPublicService?wsdl"
)

# Batch size the WS returns per call, per Popis_WS_1 2.1: "vrátí prvních 1000 akcí".
BATCH_SIZE = 1000


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Lazily build the SOAP client on first use instead of blocking on import."""
    return Client(WSDL_URL)


def _check_status(status) -> None:
    if status.stav != "OK":
        raise RuntimeError(
            f"ISIR WS returned error {status.kodChyby}: {status.popisChyby}"
        )


def get_last_podnet_id() -> int:
    """Return the ID of the most recently published event (podnet)."""
    try:
        response = _get_client().service.getIsirWsPublicPodnetPosledniId()
    except Fault as exc:
        raise RuntimeError(f"ISIR WS SOAP fault: {exc}") from exc
    _check_status(response.status)
    return int(response.cisloPosledniId[0])


def get_events(id_podnetu: int) -> list[dict]:
    """Return events with id > id_podnetu, oldest first, up to BATCH_SIZE records.

    Per Popis_WS_1 2.2: if this returns exactly BATCH_SIZE records, more may be
    waiting - callers should loop, feeding back the highest id seen, until a
    short batch comes back.
    """
    try:
        response = _get_client().service.getIsirWsPublicPodnetId(idPodnetu=id_podnetu)
    except Fault as exc:
        raise RuntimeError(f"ISIR WS SOAP fault: {exc}") from exc
    _check_status(response.status)

    events = []
    for item in response.data or []:
        events.append(
            {
                "id": int(item.id),
                "datum_zalozeni_udalosti": item.datumZalozeniUdalosti,
                "datum_zverejneni_udalosti": item.datumZverejneniUdalosti,
                "dokument_url": item.dokumentUrl,
                "spisova_znacka": item.spisovaZnacka,
                "typ_udalosti": item.typUdalosti,
                "popis_udalosti": item.popisUdalosti,
                "oddil": item.oddil,
                "cislo_v_oddilu": item.cisloVOddilu,
                "poznamka_xml": item.poznamka,
            }
        )
    return events
