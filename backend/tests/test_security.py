from datetime import timedelta

import pytest
from pydantic import SecretStr

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.timeutil import utcnow


def test_password_is_hashed_not_stored_plain():
    hashed = hash_password("a-good-password", rounds=4)

    assert hashed != "a-good-password"
    assert hashed.startswith("$2b$04$")
    assert verify_password("a-good-password", hashed)
    assert not verify_password("a-wrong-password", hashed)


def test_same_password_hashes_differently_each_time():
    assert hash_password("a-good-password", rounds=4) != hash_password("a-good-password", rounds=4)


def test_password_longer_than_bcrypt_limit_is_refused():
    with pytest.raises(ValueError):
        hash_password("x" * 73, rounds=4)
    assert not verify_password("x" * 73, hash_password("x" * 72, rounds=4))


def test_verify_handles_corrupt_hash():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_token_round_trip(settings):
    token, lifetime = create_access_token(42, "student", settings)

    assert decode_access_token(token, settings) == 42
    assert lifetime == settings.access_token_expire_minutes * 60


def test_expired_token_is_refused(settings):
    token, _ = create_access_token(42, "student", settings, now=utcnow() - timedelta(days=1))

    with pytest.raises(TokenError):
        decode_access_token(token, settings)


def test_token_from_another_secret_is_refused(settings):
    other = settings.model_copy(update={"jwt_secret_key": SecretStr("x" * 40)})
    token, _ = create_access_token(42, "student", other)

    with pytest.raises(TokenError):
        decode_access_token(token, settings)
