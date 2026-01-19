"""
Create Initial Admin User

Creates a default admin user for first-time setup.

Usage:
    python -m database.seeds.create_admin_user
"""

import asyncio
import logging
import uuid
from passlib.hash import bcrypt

from database.connection import get_async_session
from database.models import AdminUser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_admin_user() -> None:
    """Create initial admin user if none exists."""

    async with get_async_session() as session:
        # Check if any admin users exist
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(AdminUser.id)))
        count = result.scalar()

        if count > 0:
            logger.info(f"Admin users already exist ({count} found). Skipping creation.")
            return

        # Create default admin user
        username = "admin"
        password = "admin123"  # Default password - CHANGE THIS IN PRODUCTION

        password_hash = bcrypt.hash(password)

        admin_user = AdminUser(
            id=uuid.uuid4(),
            username=username,
            password_hash=password_hash,
            role="admin",
            display_name="System Administrator",
            is_active=True,
        )

        session.add(admin_user)
        await session.commit()

        logger.info("=" * 70)
        logger.info("✅ Admin user created successfully!")
        logger.info("=" * 70)
        logger.info(f"Username: {username}")
        logger.info(f"Password: {password}")
        logger.info("=" * 70)
        logger.warning("⚠️  IMPORTANT: Change the password after first login!")
        logger.info("=" * 70)


async def main() -> None:
    """Main entry point."""
    try:
        await create_admin_user()
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
