"""Tests for NDClient.paged(): offset/max pagination must not truncate against meta.counts.total."""

from nd_client import NDClient, NDCredentials


def _client() -> NDClient:
    return NDClient(NDCredentials(ip="192.0.2.1", username="admin", password="secret"))


def test_paged_follows_total_across_short_pages():
    """Server hard-caps at 10 items per response (as ND does for policies) even though the caller requests
    the default page=100 and meta.counts.total says 25: all 25 must come back, not just the first 10."""
    all_items = [{"n": i} for i in range(25)]
    requested_offsets = []

    def fake_get(path, params=None):
        offset = params["offset"]
        end = offset + 10
        requested_offsets.append(offset)
        chunk = all_items[offset:end]
        return {"things": chunk, "meta": {"counts": {"total": 25}}}

    client = _client()
    client.get = fake_get

    items = client.paged("/things", "things")

    assert items == all_items
    assert requested_offsets == [0, 10, 20]


def test_paged_stops_on_empty_chunk_when_total_unknown():
    """No meta.counts.total: pagination must stop on the first empty chunk, not loop forever."""
    all_items = [{"n": i} for i in range(15)]

    def fake_get(path, params=None):
        offset = params["offset"]
        end = offset + 10
        chunk = all_items[offset:end]
        return {"things": chunk}

    client = _client()
    client.get = fake_get

    items = client.paged("/things", "things", page=10)

    assert items == all_items
