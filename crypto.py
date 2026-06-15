"""At-rest encryption + signed tokens -- stdlib only (no new dependency).

JobMagnet stores third-party credentials (Twilio auth tokens, Google/Meta access
tokens) per tenant. Those must not sit in the database in the clear. This module seals
them with authenticated encryption keyed off JOBMAGNET_SECRETS_KEY, and also issues the
HMAC tokens that make public links (the CAN-SPAM unsubscribe link) un-enumerable.

Same honesty discipline as every other seam: with no key set (dev/demo), encryption is
INACTIVE and values pass through in the clear -- so nothing breaks locally and the
Connections UI can tell the owner their secrets aren't encrypted yet. The moment a key is
set, new writes are sealed; reads transparently handle both sealed and legacy-plaintext
values, so turning encryption on never strands existing data.

Construction (encrypt-then-MAC, all from hashlib/hmac since stdlib has no AEAD):
  enc_key = SHA256("jm-enc-v1" | master);  mac_key = SHA256("jm-mac-v1" | master)
  keystream = HMAC-SHA256(enc_key, nonce | counter) blocks;  ct = pt XOR keystream
  tag = HMAC-SHA256(mac_key, nonce | ct);  token = "enc:v1:" + b64(nonce | ct | tag)
A wrong/absent key or any tampering fails the constant-time tag check -> we refuse to
return forged plaintext.
"""
import base64
import hashlib
import hmac

from config import SECRETS_KEY, SECRET_KEY

_PREFIX = "enc:v1:"
_NONCE = 16
_TAG = 32


def secrets_active():
    """True when a secrets key is configured, so credentials are sealed at rest."""
    return bool(SECRETS_KEY)


def _keys():
    master = hashlib.sha256(SECRETS_KEY.encode("utf-8")).digest()
    enc = hashlib.sha256(b"jm-enc-v1" + master).digest()
    mac = hashlib.sha256(b"jm-mac-v1" + master).digest()
    return enc, mac


def _keystream(enc_key, nonce, n):
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:n])


def _xor(data, stream):
    return bytes(a ^ b for a, b in zip(data, stream))


def encrypt(plaintext):
    """Seal a string. Returns an 'enc:v1:...' token when a key is set, else the plaintext
    unchanged (dev: honest, readable, no key)."""
    if plaintext is None:
        plaintext = ""
    if not secrets_active():
        return plaintext
    import os
    enc_key, mac_key = _keys()
    nonce = os.urandom(_NONCE)
    pt = plaintext.encode("utf-8")
    ct = _xor(pt, _keystream(enc_key, nonce, len(pt)))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode("ascii")


def is_sealed(value):
    return isinstance(value, str) and value.startswith(_PREFIX)


def decrypt(value):
    """Open a value. Sealed tokens are verified + decrypted; a legacy plaintext value
    (no prefix) is returned as-is. Returns None if a sealed token can't be opened
    (no/wrong key, or tampering) so forged data is never trusted."""
    if not is_sealed(value):
        return value
    if not secrets_active():
        return None
    try:
        raw = base64.urlsafe_b64decode(value[len(_PREFIX):].encode("ascii"))
    except (ValueError, TypeError):
        return None
    if len(raw) < _NONCE + _TAG:
        return None
    nonce, ct, tag = raw[:_NONCE], raw[_NONCE:-_TAG], raw[-_TAG:]
    enc_key, mac_key = _keys()
    expected = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        return None
    try:
        return _xor(ct, _keystream(enc_key, nonce, len(ct))).decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---- Signed ids (for public, un-enumerable links) -------------------------
def sign_id(purpose, ident):
    """A short HMAC tag binding `ident` to `purpose`, so a public link can't be guessed
    or enumerated. Keyed by the app SECRET_KEY (stable across restarts)."""
    msg = f"{purpose}:{ident}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]


def verify_id(purpose, ident, token):
    return hmac.compare_digest(sign_id(purpose, ident), str(token or ""))
