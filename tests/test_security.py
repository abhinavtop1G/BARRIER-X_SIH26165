"""Authentication and rate limiting."""

from __future__ import annotations

import pytest

from api.security import TokenBucket, key_id
from tests.conftest import SEVERE

KEYS = "test-key-one,test-key-two"


def test_bucket_allows_burst_then_refuses():
    b = TokenBucket(rate_per_min=60, burst=3)
    assert [b.take("a", now=0.0)[0] for _ in range(3)] == [True, True, True]
    allowed, wait = b.take("a", now=0.0)
    assert allowed is False and wait > 0


def test_bucket_refills_over_time():
    b = TokenBucket(rate_per_min=60, burst=1)
    assert b.take("a", now=0.0)[0] is True
    assert b.take("a", now=0.5)[0] is False, "must not refill early"
    assert b.take("a", now=1.0)[0] is True


def test_bucket_never_exceeds_burst():
    b = TokenBucket(rate_per_min=600, burst=2)
    b.take("a", now=0.0)
    assert [b.take("a", now=1000.0)[0] for _ in range(3)] == [True, True, False]


def test_buckets_are_per_caller():
    b = TokenBucket(rate_per_min=60, burst=1)
    assert b.take("alice", now=0.0)[0] is True
    assert b.take("bob", now=0.0)[0] is True, "one caller must not exhaust another"
    assert b.take("alice", now=0.0)[0] is False


def test_key_id_is_stable_and_not_the_key():
    assert key_id("hunter2") == key_id("hunter2")
    assert key_id("hunter2") != key_id("hunter3")
    assert "hunter2" not in key_id("hunter2"), "never leak the key into logs"


def test_open_by_default_but_says_so(make_client):
    c = make_client(SIF_RATE_LIMIT=0)
    assert c.get("/health").json()["auth_enabled"] is False


def test_auth_enabled_when_keys_are_set(make_client):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=0)
    assert c.get("/health").json()["auth_enabled"] is True


@pytest.mark.parametrize("headers", [
    {},
    {"X-API-Key": "wrong"},
    {"Authorization": "Bearer wrong"},
    {"Authorization": "Basic test-key-one"},
])
def test_bad_credentials_are_rejected(make_client, headers):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=0)
    r = c.post("/score", json={"narrative": SEVERE}, headers=headers)
    assert r.status_code == 401
    assert "detail" in r.json()


def test_health_and_docs_stay_reachable_without_a_key(make_client):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=0)
    for path in ("/health", "/", "/openapi.json"):
        assert c.get(path).status_code == 200, f"{path} must stay probe-able"


@pytest.mark.model
@pytest.mark.parametrize("headers", [
    {"X-API-Key": "test-key-one"},
    {"Authorization": "Bearer test-key-two"},
])
def test_valid_credentials_are_accepted(make_client, headers):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=0)
    assert c.post("/score", json={"narrative": SEVERE},
                  headers=headers).status_code == 200


@pytest.mark.model
def test_rate_limit_returns_429_with_retry_after(make_client):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=6, SIF_RATE_BURST=2)
    h = {"X-API-Key": "test-key-one"}
    codes = [c.post("/score", json={"narrative": SEVERE}, headers=h).status_code
             for _ in range(5)]
    assert codes[:2] == [200, 200]
    assert 429 in codes

    r = c.post("/score", json={"narrative": SEVERE}, headers=h)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


@pytest.mark.model
def test_rate_limit_is_per_key(make_client):
    c = make_client(SIF_API_KEYS=KEYS, SIF_RATE_LIMIT=6, SIF_RATE_BURST=2)
    for _ in range(4):
        c.post("/score", json={"narrative": SEVERE},
               headers={"X-API-Key": "test-key-one"})
    assert c.post("/score", json={"narrative": SEVERE},
                  headers={"X-API-Key": "test-key-one"}).status_code == 429
    assert c.post("/score", json={"narrative": SEVERE},
                  headers={"X-API-Key": "test-key-two"}).status_code == 200
