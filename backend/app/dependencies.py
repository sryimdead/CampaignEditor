from collections.abc import Iterator

from .config import get_settings
from .keitaro import KeitaroClient


def get_keitaro() -> Iterator[KeitaroClient]:
    k = get_settings().keitaro
    client = KeitaroClient(
        base_url=str(k.base_url),
        api_key=k.api_key.get_secret_value(),
        api_key_header=k.api_key_header,
        timeout=k.timeout_seconds,
    )
    try:
        yield client
    finally:
        client.close()
