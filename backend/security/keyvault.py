"""Per-user API key storage: Fernet-encrypted at rest.

End-users may bring their own transcription key (Gemini / Groq) via
Settings. The key is sent with the upload over HTTPS as a form field
(never a query param — query strings land in access logs), encrypted
here with a server-side key, and stored only as ciphertext in
video.meta. The worker decrypts it transiently at transcribe time and
never logs it.

The encryption key comes from the USER_KEY_ENCRYPTION_KEY env var
(Fernet key, urlsafe base64 32 bytes) when set. When it is NOT set, the
key is derived from the SUPABASE_KEY env var (already present on the API
+ worker) via HKDF — so user-key storage works with zero extra setup.
That derivation is safe here: anyone holding SUPABASE_KEY already has
full DB access, so it adds no new trust boundary; the encryption still
protects the ciphertext against a DB-only leak (backup, dashboard
viewer) that does not include the service key. If neither env var is
set, user-key storage is refused outright — keys are never stored in
plaintext.
"""
import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _fernet() -> Fernet:
    raw = os.environ.get("USER_KEY_ENCRYPTION_KEY", "")
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception as exc:
            raise RuntimeError(
                "USER_KEY_ENCRYPTION_KEY is not a valid Fernet key") from exc
    service_key = os.environ.get("SUPABASE_KEY", "")
    if not service_key:
        raise RuntimeError(
            "neither USER_KEY_ENCRYPTION_KEY nor SUPABASE_KEY is set: "
            "user-key storage is not configured on this server")
    derived = HKDF(algorithm=hashes.SHA256(), length=32,
                   salt=b"ai-video-recap-user-key-v1",
                   info=b"transcription-key-encryption").derive(
                       service_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("stored transcription key cannot be decrypted "
                           "(wrong USER_KEY_ENCRYPTION_KEY?)") from exc
