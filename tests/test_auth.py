"""Password hashing and signed session tokens — the security-critical core."""
import auth


def test_hash_roundtrip():
    h = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("correct horse battery staple", h)
    assert not auth.verify_password("wrong password", h)


def test_hash_is_salted():
    # Same password hashed twice must differ (random salt) but both verify.
    a = auth.hash_password("hunter2")
    b = auth.hash_password("hunter2")
    assert a != b
    assert auth.verify_password("hunter2", a)
    assert auth.verify_password("hunter2", b)


def test_verify_handles_garbage_without_raising():
    assert auth.verify_password("x", "") is False
    assert auth.verify_password("x", "no-dollar-sign") is False
    assert auth.verify_password("x", None) is False


def _user(pw="abc", totp="SEED"):
    return {"Id": 7, "PasswordHash": pw, "TotpSecret": totp}


def test_session_token_roundtrip():
    u = _user()
    token = auth.make_session_token(u)
    data = auth.load_session_token(token)
    assert data is not None
    assert data["uid"] == 7
    assert data["v"] == auth.auth_version(u)


def test_tampered_token_rejected():
    token = auth.make_session_token(_user())
    assert auth.load_session_token(token[:-3] + "zzz") is None
    assert auth.load_session_token("not-a-token") is None


def test_auth_version_changes_with_credentials():
    base = auth.auth_version(_user("hashA", "seedA"))
    assert base == auth.auth_version(_user("hashA", "seedA"))     # stable
    assert base != auth.auth_version(_user("hashB", "seedA"))     # password changed
    assert base != auth.auth_version(_user("hashA", "seedB"))     # 2FA changed


def test_token_invalidated_by_credential_change():
    # A token minted before a password change must fail the version check on restore.
    old = _user("oldhash", "seed")
    token = auth.make_session_token(old)
    data = auth.load_session_token(token)
    changed = _user("newhash", "seed")
    assert data["v"] != auth.auth_version(changed)
