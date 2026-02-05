#!/usr/bin/env python3
"""
Password Reset Utility for Speedarr

Usage:
    docker exec -it speedarr python -m app.utils.reset_password <username>

This will prompt for a new password interactively (password not logged).
"""

import sys
import asyncio
import getpass
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Suppress logging during password reset
import logging
logging.disable(logging.CRITICAL)

from app.models.user import User
from app.api.auth import get_password_hash


DATABASE_URL = "sqlite+aiosqlite:///data/speedarr.db"


async def reset_password(username: str, new_password: str) -> bool:
    """Reset a user's password."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find user
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Update password hash
        user.password_hash = get_password_hash(new_password)
        await session.commit()
        return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.utils.reset_password <username>")
        print("\nThis utility resets a user's password for Speedarr.")
        print("The password is entered interactively and never logged.")
        sys.exit(1)

    username = sys.argv[1]

    print(f"\nSpeedarr Password Reset")
    print(f"========================")
    print(f"Resetting password for user: {username}\n")

    # Get password interactively (not logged)
    try:
        new_password = getpass.getpass("Enter new password: ")
        confirm_password = getpass.getpass("Confirm new password: ")
    except KeyboardInterrupt:
        print("\n\nPassword reset cancelled.")
        sys.exit(1)

    if not new_password:
        print("\nError: Password cannot be empty.")
        sys.exit(1)

    if new_password != confirm_password:
        print("\nError: Passwords do not match.")
        sys.exit(1)

    if len(new_password) < 6:
        print("\nError: Password must be at least 6 characters.")
        sys.exit(1)

    # Reset password
    success = asyncio.run(reset_password(username, new_password))

    if success:
        print(f"\nPassword for '{username}' has been reset successfully.")
    else:
        print(f"\nError: User '{username}' not found.")
        sys.exit(1)


if __name__ == "__main__":
    main()
