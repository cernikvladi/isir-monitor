import time
from zeep import Client

WSDL_URL = (
    "https://isir.justice.cz:8443/"
    "isir_public_ws/IsirWsPublicService?wsdl"
)

client = Client(WSDL_URL)


def get_last_podnet_id() -> dict:
    start = time.time()

    response = client.service.getIsirWsPublicPodnetPosledniId()

    elapsed = time.time() - start

    if response.status.stav != "OK":
        raise RuntimeError(response.status.popisChyby)

    return {
        "last_id": int(response.cisloPosledniId[0]),
        "elapsed_seconds": round(elapsed, 2),
    }