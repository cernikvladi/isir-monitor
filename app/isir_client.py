from zeep import Client

WSDL_URL = (
    "https://isir.justice.cz:8443/"
    "isir_public_ws/IsirWsPublicService?wsdl"
)


def get_last_podnet_id():
    client = Client(WSDL_URL)
    response = client.service.getIsirWsPublicPodnetPosledniId()
    return {
        "response_type": str(type(response)),
        "response": str(response),
        "last_id": str(response.cisloPosledniId),
    }


def list_operations() -> list[str]:
    client = Client(WSDL_URL)
    operations: list[str] = []
    for service in client.wsdl.services.values():
        for port in service.ports.values():
            operations.extend(port.binding._operations.keys())
    return sorted(set(operations))



