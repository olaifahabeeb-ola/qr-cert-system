import json
import base64
import os
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

KEY_DIR          = os.path.join(os.path.dirname(__file__), 'keys')
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, 'private.pem')
PUBLIC_KEY_PATH  = os.path.join(KEY_DIR, 'public.pem')


def generate_keys():
    os.makedirs(KEY_DIR, exist_ok=True)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    with open(PRIVATE_KEY_PATH, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(PUBLIC_KEY_PATH, 'wb') as f:
        f.write(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    return private_key, private_key.public_key()


def load_private_key():
    with open(PRIVATE_KEY_PATH, 'rb') as f:
        return serialization.load_pem_private_key(
            f.read(), password=None, backend=default_backend()
        )


def load_public_key():
    with open(PUBLIC_KEY_PATH, 'rb') as f:
        return serialization.load_pem_public_key(
            f.read(), backend=default_backend()
        )


def keys_exist():
    return os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH)


def sign_certificate(cert_data: dict) -> dict:
    private_key = load_private_key()
    canonical   = json.dumps(
        cert_data, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    signature = private_key.sign(
        canonical,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return {
        'data':      cert_data,
        'signature': base64.b64encode(signature).decode('utf-8')
    }


def verify_certificate(payload: dict):
    try:
        if not keys_exist():
            return False, "Public key not found."

        cert_data = payload.get('data')
        sig_b64   = payload.get('signature')

        if not cert_data or not sig_b64:
            return False, "Invalid payload: missing data or signature."

        public_key = load_public_key()
        canonical  = json.dumps(
            cert_data, sort_keys=True, separators=(',', ':')
        ).encode('utf-8')
        signature  = base64.b64decode(sig_b64)

        public_key.verify(
            signature,
            canonical,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True, "Certificate is AUTHENTIC. Signature verified successfully."

    except InvalidSignature:
        return False, "INVALID certificate. Signature does not match — this certificate may be forged or tampered with."
    except Exception as e:
        return False, f"Verification error: {str(e)}"


def get_public_key_pem() -> str:
    if not keys_exist():
        return ""
    with open(PUBLIC_KEY_PATH, 'r') as f:
        return f.read()