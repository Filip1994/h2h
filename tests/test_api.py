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


def test_api_archives_successful_network_response(settings, monkeypatch) -> None:
    def fake_urlopen(_request, timeout):
        assert timeout == 20
        return FakeResponse()

    monkeypatch.setattr("quantbot.api.urlopen", fake_urlopen)
    client = APIFootballClient(settings)
    assert client.get("fixtures", {"id": 42}, ttl_seconds=60) == [{"id": 1}]

    archives = list((settings.root / "data" / "raw_api").glob("*.jsonl"))
    assert len(archives) == 1
    records = [
        json.loads(line)
        for line in archives[0].read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    record = records[0]
    assert record["schema_version"] == 1
    assert record["endpoint"] == "fixtures"
    assert record["params"] == {"id": 42}
    assert record["payload"]["response"] == [{"id": 1}]
    assert "x-apisports-key" not in record["request_url"]


def test_api_cache_hit_does_not_duplicate_archive(settings, monkeypatch) -> None:
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse()

    monkeypatch.setattr("quantbot.api.urlopen", fake_urlopen)
    client = APIFootballClient(settings)
    client.get("fixtures", {"id": 99}, ttl_seconds=60)
    client.get("fixtures", {"id": 99}, ttl_seconds=60)

    archives = list((settings.root / "data" / "raw_api").glob("*.jsonl"))
    records = [
        json.loads(line)
        for line in archives[0].read_text(encoding="utf-8").splitlines()
    ]
    assert calls == 1
    assert len(records) == 1
