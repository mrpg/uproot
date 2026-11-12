# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Admin passwords stored as Argon2id hashes (RFC 9106) in PHC string format."""

import base64
import binascii
import logging
import re
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from argon2.profiles import RFC_9106_LOW_MEMORY

MIN_PASSWORD_LENGTH: int = 5

HASHER = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)
PHC = re.compile(
    r"\$argon2id\$v=19\$m=([1-9][0-9]*),t=([1-9][0-9]*),p=([1-9][0-9]*)"
    r"\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)"
)


def b64decode(data: str) -> bytes:
    """Decode unpadded base64 as used by the PHC string format."""
    return base64.b64decode(data + "=" * (-len(data) % 4), validate=True)


def phc_valid(phc: str) -> bool:
    """Check that *phc* is an Argon2id hash within the bounds of RFC 9106."""
    if (match := PHC.fullmatch(phc)) is None:
        return False

    m, t, p = (int(match[i]) for i in (1, 2, 3))

    try:
        salt, tag = b64decode(match[4]), b64decode(match[5])
    except binascii.Error:
        return False

    return (
        1 <= p < 2**24
        and 8 * p <= m < 2**32
        and 1 <= t < 2**32
        and len(salt) >= 8
        and len(tag) >= 4
    )


@dataclass(frozen=True, slots=True)
class Argon2id:
    """An admin password given as Argon2id hash, e.g., from `uproot hash-password`."""

    phc: str

    def __post_init__(self) -> None:
        if not isinstance(self.phc, str) or not phc_valid(self.phc):
            raise ValueError(
                "Expected an Argon2id hash such as '$argon2id$v=19$m=65536,t=3,"
                "p=4$<salt>$<hash>'. Note that shells expand '$', so quote hashes "
                "in single quotes there and in .env files."
            )

    def verify(self, password: str) -> bool:
        try:
            return HASHER.verify(self.phc, password)
        except (VerifyMismatchError, UnicodeEncodeError):
            return False
        except VerificationError:
            logging.getLogger("uproot").exception("Argon2id verification failed")
            return False


def hash_password(password: str) -> Argon2id:
    return Argon2id(HASHER.hash(password))


# As costly to verify as hashes from hash_password (salt and tag are all zeros),
# for login attempts without a hash to verify
DUMMY_HASH = Argon2id(
    f"$argon2id$v=19$m={HASHER.memory_cost},t={HASHER.time_cost},"
    f"p={HASHER.parallelism}${'A' * 22}${'A' * 43}"
)
