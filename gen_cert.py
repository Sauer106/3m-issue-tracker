"""Generate a self-signed TLS certificate for the app into certs/.

Produces:
    certs/key.pem         private key (keep on the server)
    certs/cert.pem        certificate served by Streamlit
    certs/3m-tracker.cer  DER copy for client machines to trust

Client machines trust it once (elevated prompt):
    certutil -addstore -f Root 3m-tracker.cer

If you later obtain a CA-issued certificate, replace cert.pem/key.pem
with the CA-issued pair and restart the app -- nothing else changes.
"""
import datetime
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERT_DIR = Path(__file__).resolve().parent / "certs"
YEARS = 5


def main():
    CERT_DIR.mkdir(exist_ok=True)
    fqdn = socket.getfqdn()
    seen = set()
    sans = [n for n in (fqdn, socket.gethostname(), "localhost")
            if not (n.lower() in seen or seen.add(n.lower()))]

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, fqdn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * YEARS))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in sans]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )

    (CERT_DIR / "key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    (CERT_DIR / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (CERT_DIR / "3m-tracker.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    print(f"Wrote self-signed cert for {', '.join(sans)} (valid {YEARS} years) to {CERT_DIR}")


if __name__ == "__main__":
    main()
