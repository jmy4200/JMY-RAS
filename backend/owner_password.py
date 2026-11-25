"""Generate and verify the configured JMY-RAS owner password hash."""

import base64
import getpass
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
MIN_ITERATIONS = 100_000
MAX_ITERATIONS = 2_000_000


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not isinstance(password, str) or len(password) < 14:
        raise ValueError("Owner password must contain at least 14 characters")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError("PBKDF2 iteration count is outside the allowed range")

    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    hash_text = base64.urlsafe_b64encode(derived).decode("ascii").rstrip("=")
    return ALGORITHM + "$" + str(iterations) + "$" + salt_text + "$" + hash_text


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded_hash.split("$")
        iterations = int(iterations_text)
        if algorithm != ALGORITHM or not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
            return False

        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(
            expected_text + "=" * (-len(expected_text) % 4)
        )
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def main():
    password = getpass.getpass("New JMY-RAS owner password (14+ characters): ")
    confirmation = getpass.getpass("Confirm owner password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    try:
        encoded = hash_password(password)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print("\nAdd this line to your private .env file or deployment secret store:")
    print("JMY_OWNER_PASSWORD_HASH=" + encoded)
    print("\nDo not commit this hash or share the password.")


if __name__ == "__main__":
    main()
