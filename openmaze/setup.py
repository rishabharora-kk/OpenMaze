"""Create fresh local demo secrets. Never overwrite an existing state directory."""

import os
from pathlib import Path
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .common import encode


def initialize(state):
    state = Path(state)
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ("backend", "decoy", "logs"):
        (state / name).mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    files = {
        "auth.json": encode({"alpha": secrets.token_urlsafe(32), "beta": secrets.token_urlsafe(32)}),
        "signing.key": key.private_bytes_raw(),
        "verify.key": key.public_key().public_bytes_raw(),
        "decoy.seed": os.urandom(32),
    }
    for name, content in files.items():
        with (state / name).open("xb") as output:
            os.chmod(output.fileno(), 0o600)
            output.write(content)
