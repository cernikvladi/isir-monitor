from zeep import Client

WSDL_URL = (
    "https://isir.justice.cz:8443/"
    "isir_public_ws/IsirWsPublicService?wsdl"
)


def get_last_podnet_id() -> int:
    client = Client(WSDL_URL)
    response = client.service.getIsirWsPublicPodnetPosledniId()

    if response.status.stav != "OK":
        raise RuntimeError(
            f"ISIR chyba {response.status.kodChyby}: "
            f"{response.status.popisChyby}"
        )

    if not response.cisloPosledniId:
        raise RuntimeError("ISIR nevrátil poslední ID.")

    return int(response.cisloPosledniId[0])


def list_operations() -> list[str]:
    client = Client(WSDL_URL)

    operations: list[str] = []

    for service in client.wsdl.services.values():
        for port in service.ports.values():
            operations.extend(port.binding._operations.keys())

    return sorted(set(operations))



