from zeep import Client


WSDL_URL = (
    "https://isir.justice.cz:8443/"
    "isir_public_ws/IsirWsPublicService?wsdl"
)


def get_last_podnet_id() -> int:
    client = Client(WSDL_URL)

    response = client.service.getIsirWsPublicPosledniId()

    return int(response.cisloPosledniId)