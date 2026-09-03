"""Generate secure environment values for the centralized clinic login."""

import getpass
import secrets
from argon2 import PasswordHasher


def main() -> None:
    username = input("Clinic username [smritiraj-clinic]: ").strip() or "smritiraj-clinic"
    password = getpass.getpass("Clinic password (at least 14 characters): ")
    confirmation = getpass.getpass("Confirm clinic password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 14:
        raise SystemExit("Password must be at least 14 characters.")

    print("\nAdd these values to .env locally or Railway Variables:\n")
    print(f"CLINIC_USERNAME={username}")
    print(f"CLINIC_PASSWORD_HASH={PasswordHasher().hash(password)}")
    print(f"SESSION_SECRET_KEY={secrets.token_urlsafe(48)}")
    print("SESSION_VERSION=1")


if __name__ == "__main__":
    main()
