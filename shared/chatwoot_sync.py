"""
MSI Automotive - Chatwoot Contact Synchronization Service.

Centralizes the logic to sync User data to Chatwoot contacts.
Used by both admin API and agent tools to maintain consistency
between the MSI-a database and Chatwoot.

Synced fields:
- name (first_name + last_name)
- email
- custom_attributes.tipo (client_type mapped to "Particular"/"Profesional")
"""

import logging
from typing import TYPE_CHECKING

from shared.chatwoot_client import ChatwootClient

if TYPE_CHECKING:
    from database.models import User

logger = logging.getLogger(__name__)


async def sync_user_to_chatwoot(
    user: "User",
    save_contact_id: bool = False,
) -> bool:
    """
    Synchronize User data to Chatwoot contact.

    This function syncs the following fields to Chatwoot:
    - name: Concatenation of first_name and last_name
    - email: User's email address
    - custom_attributes.tipo: "Particular" or "Profesional" based on client_type

    The sync is best-effort: errors are logged but do not raise exceptions.

    Args:
        user: User model instance with data to sync. Must have at minimum
              the 'phone' field populated for contact lookup.
        save_contact_id: If True and contact is found by phone lookup,
                        the chatwoot_contact_id will be saved to the user object.
                        Note: Caller is responsible for committing the session.

    Returns:
        True if sync was successful, False otherwise.

    Example:
        ```python
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            user.first_name = "Juan"
            await session.commit()

            # Sync to Chatwoot (best-effort)
            await sync_user_to_chatwoot(user)
        ```
    """
    chatwoot_client = ChatwootClient()
    contact_id = user.chatwoot_contact_id

    # Try to find contact by phone if not stored
    if not contact_id:
        try:
            contact = await chatwoot_client.find_contact_by_phone(user.phone)
            if contact:
                contact_id = contact["id"]
                if save_contact_id:
                    user.chatwoot_contact_id = contact_id
                    logger.info(
                        f"Discovered chatwoot_contact_id={contact_id} for user {user.id}",
                        extra={
                            "user_id": str(user.id),
                            "chatwoot_contact_id": contact_id,
                        },
                    )
        except Exception as e:
            logger.warning(
                f"Failed to find Chatwoot contact by phone for user {user.id}: {e}",
                extra={"user_id": str(user.id), "phone": user.phone},
            )
            return False

    if not contact_id:
        logger.debug(
            f"No Chatwoot contact found for user {user.id} (phone: {user.phone})",
            extra={"user_id": str(user.id)},
        )
        return False

    # Build sync data
    tipo = "Profesional" if user.client_type == "professional" else "Particular"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None

    try:
        await chatwoot_client.update_contact(
            contact_id=contact_id,
            name=name,
            email=user.email,
            custom_attributes={"tipo": tipo},
        )
        logger.info(
            f"Synced user {user.id} to Chatwoot contact {contact_id}",
            extra={
                "user_id": str(user.id),
                "chatwoot_contact_id": contact_id,
                "synced_fields": {
                    "name": name,
                    "email": user.email,
                    "tipo": tipo,
                },
            },
        )
        return True
    except Exception as e:
        logger.warning(
            f"Failed to sync user {user.id} to Chatwoot contact {contact_id}: {e}",
            extra={
                "user_id": str(user.id),
                "chatwoot_contact_id": contact_id,
            },
            exc_info=True,
        )
        return False
