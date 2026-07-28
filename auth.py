"""Password hashing/verification and signed session tokens (stdlib + itsdangerous)."""
import hashlib
import hmac
import os
from pathlib import Path

from itsdangerous import BadData, URLSafeTimedSerializer

ITERATIONS = 200_000
SESSION_MAX_AGE = 12 * 3600  # how long a "remember me" session cookie stays valid
_SECRET_PATH = Path(__file__).resolve().parent / "session_secret.key"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


# ---------------------------------------------------------------- session tokens

def _session_secret() -> str:
    if not _SECRET_PATH.exists():
        _SECRET_PATH.write_text(os.urandom(32).hex())
    return _SECRET_PATH.read_text().strip()


def auth_version(user) -> str:
    """Fingerprint of the user's credentials; changing password or resetting 2FA
    changes it, which invalidates any session tokens issued before the change."""
    basis = (user["PasswordHash"] or "") + "|" + (user["TotpSecret"] or "")
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def make_session_token(user) -> str:
    return URLSafeTimedSerializer(_session_secret()).dumps(
        {"uid": user["Id"], "v": auth_version(user)})


def load_session_token(token):
    """Return the token payload if the signature is valid and it hasn't expired."""
    try:
        return URLSafeTimedSerializer(_session_secret()).loads(token, max_age=SESSION_MAX_AGE)
    except BadData:
        return None
