import json
from urllib.error import URLError

from quantbot.api import APIFootballClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps({"errors": [], "response": [{"id": 1}]}).encode()


def test_api_cache_prevents_duplicate_request(settings, monkeypatch) -> None:
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 20
        calls += 1
        return FakeResponse()

    monkeypatch.setattr("quantbot.api.urlopen", fake_urlopen)
    client = APIFootballClient(settings)
    first = client.get("fixtures", {"id": 1}, ttl_seconds=60)
    second = client.get("fixtures", {"id": 1}, ttl_seconds=60)
    assert first == second == [{"id": 1}]
    assert calls == 1
    assert client.request_count == 1


def test_api_retries_transient_network_error(settings, monkeypatch) -> None:
    calls = 0
    delays: list[float] = []

    def flaky_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 20
        calls += 1
        if calls == 1:
            raise URLError("temporary")
        return FakeResponse()

    monkeypatch.setattr("quantbot.api.urlopen", flaky_urlopen)
    monkeypatch.setattr("quantbot.api.time.sleep", delays.append)
    client = APIFootballClient(settings)
    assert client.get("fixtures", {"id": 7}) == [{"id": 1}]
    assert calls == 2
    assert client.request_count == 2
    assert delays == [settings.api_retry_base_seconds]
