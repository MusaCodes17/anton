"""
Tests for R9.2 automatic sign-out on login-password change:
auth_admin.check_password_rotation (boot-time fingerprint comparison).

Service-level. One private in-memory DB backs the settings `db`, and is
swapped into `sessions` / `oauth` so the purge acts on the same data.
"""
import hashlib
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import models
import app.services.oauth as oauth_svc
import app.services.sessions as sessions_svc
from app.services import auth_admin, settings as settings_svc
from app.services.auth_admin import PASSWORD_FINGERPRINT_KEY

OLD = "old-passphrase-for-tests"
NEW = "new-passphrase-for-tests"


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(sessions_svc, "SessionLocal", maker)
    monkeypatch.setattr(oauth_svc, "SessionLocal", maker)
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", OLD)
    session = maker()
    yield session
    session.close()
    engine.dispose()


def seed(db):
    """One browser session and one OAuth token."""
    db.add(models.AuthSession(session_hash="s" * 64, expires_at=time.time() + 3600))
    db.add(models.OAuthToken(
        token_hash=hashlib.sha256(b"t").hexdigest(), token_type="access",
        client_id="c", expires_at=time.time() + 3600,
    ))
    db.commit()


def counts(db):
    db.expire_all()
    return (db.query(models.AuthSession).count(), db.query(models.OAuthToken).count())


def stored(db):
    db.expire_all()
    return settings_svc.get_setting(db, PASSWORD_FINGERPRINT_KEY)


def test_first_boot_stores_fingerprint_without_purging(env):
    seed(env)
    assert auth_admin.check_password_rotation(env) is False
    assert stored(env).startswith("scrypt$")
    assert counts(env) == (1, 1)


def test_same_password_is_noop(env):
    auth_admin.check_password_rotation(env)
    first = stored(env)
    seed(env)
    assert auth_admin.check_password_rotation(env) is False
    assert counts(env) == (1, 1)
    assert stored(env) == first


def test_changed_password_signs_out_everywhere(env, monkeypatch):
    auth_admin.check_password_rotation(env)
    old_fp = stored(env)
    seed(env)
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", NEW)
    assert auth_admin.check_password_rotation(env) is True
    assert counts(env) == (0, 0)
    new_fp = stored(env)
    assert new_fp != old_fp
    assert auth_admin._matches(NEW, new_fp)
    assert not auth_admin._matches(OLD, new_fp)
    # The next boot with the new password is quiet.
    seed(env)
    assert auth_admin.check_password_rotation(env) is False
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_password_does_nothing(env, monkeypatch, value):
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", value)
    seed(env)
    assert auth_admin.check_password_rotation(env) is False
    assert stored(env) is None
    assert counts(env) == (1, 1)


def test_fingerprint_is_salted_and_not_plaintext():
    a = auth_admin._fingerprint(OLD, b"\x01" * 16)
    b = auth_admin._fingerprint(OLD, b"\x02" * 16)
    assert a.startswith("scrypt$")
    assert OLD not in a
    assert a != b
    assert auth_admin._matches(OLD, a)


def test_stored_fingerprint_differs_between_installs(env):
    auth_admin.check_password_rotation(env)
    first = stored(env)
    env.query(models.AppSettings).delete()
    env.commit()
    auth_admin.check_password_rotation(env)
    assert stored(env) != first
    assert OLD not in stored(env)


@pytest.mark.parametrize("bad", ["garbage", "scrypt$zz$zz", "sha256$ab$cd", "scrypt$ab"])
def test_malformed_stored_value_is_treated_as_change(env, bad):
    # Fail safe: a value we cannot verify might hide a rotation, so purge and re-store.
    settings_svc.set_setting(env, PASSWORD_FINGERPRINT_KEY, bad)
    env.commit()
    seed(env)
    assert auth_admin.check_password_rotation(env) is True
    assert counts(env) == (0, 0)
    assert auth_admin._matches(OLD, stored(env))
