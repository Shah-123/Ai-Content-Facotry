"""Password hashing and session tokens for the login/signup pages."""

import time

from api import users


def test_password_roundtrip_and_rejection():
    stored = users.hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert "correct horse battery" not in stored      # never stored in the clear
    assert users.verify_password("correct horse battery", stored) is True
    assert users.verify_password("Correct horse battery", stored) is False
    assert users.verify_password("", stored) is False


def test_each_hash_gets_its_own_salt():
    """Two accounts with the same password must not share a hash."""
    assert users.hash_password("same-password") != users.hash_password("same-password")


def test_malformed_hash_does_not_raise(monkeypatch):
    for junk in ("", "not-a-hash", "scrypt$zz$zz", "bcrypt$a$b"):
        assert users.verify_password("anything", junk) is False


def test_token_roundtrip(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    token = users.make_token("user-123")
    assert users.user_id_from_token(token) == "user-123"


def test_tampered_or_foreign_token_is_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    token = users.make_token("user-123")

    payload, _, signature = token.rpartition(".")
    assert users.user_id_from_token(f"{payload}.{'0' * len(signature)}") is None
    assert users.user_id_from_token(f"{payload}x.{signature}") is None
    assert users.user_id_from_token("garbage") is None
    assert users.user_id_from_token(None) is None

    # A token signed with a different secret must not validate here.
    monkeypatch.setenv("AUTH_SECRET", "another-secret")
    assert users.user_id_from_token(token) is None


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    assert users.user_id_from_token(users.make_token("user-123", ttl=-1)) is None
    assert users.user_id_from_token(users.make_token("user-123", ttl=60)) == "user-123"


def test_public_view_never_leaks_the_hash():
    row = {"id": "u1", "email": "a@b.co", "name": "A", "password_hash": "scrypt$x$y",
           "created_at": "2026-01-01"}
    assert "password_hash" not in users._public(row)
