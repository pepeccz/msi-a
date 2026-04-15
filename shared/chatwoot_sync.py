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
import uuid
from typing import TYPE_CHECKING, Any

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
            email=user.email or None,  # Converts "" to None — never send empty email
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


async def sync_agent_to_chatwoot(
    admin_user_id: uuid.UUID,
    action: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    chatwoot_agent_id: int | None = None,
) -> bool:
    """
    Best-effort sync of an admin user (agent) to Chatwoot.

    Actions:
      - "create": Create agent in Chatwoot, write back chatwoot_agent_id to DB
      - "update": Update agent name/email in Chatwoot
      - "delete": Delete agent from Chatwoot

    Never raises — all exceptions caught and logged.
    """
    try:
        chatwoot = ChatwootClient()

        if action == "create":
            if not email:
                logger.warning(
                    "Cannot create Chatwoot agent without email",
                    extra={"admin_user_id": str(admin_user_id)},
                )
                return False

            name = display_name or "Agent"
            agent = await chatwoot.create_agent(name=name, email=email)

            if agent is None:
                logger.warning(
                    f"Chatwoot returned None when creating agent for admin_user_id={admin_user_id} "
                    f"(possible 422 — email already exists or validation error)",
                    extra={"admin_user_id": str(admin_user_id), "email": email},
                )
                return False

            if "id" in agent:
                from database.connection import get_async_session
                from database.models import AdminUser

                async with get_async_session() as session:
                    admin_user = await session.get(AdminUser, admin_user_id)
                    if admin_user:
                        admin_user.chatwoot_agent_id = agent["id"]
                        await session.commit()
                        logger.info(
                            f"Created Chatwoot agent for admin_user_id={admin_user_id}, "
                            f"chatwoot_agent_id={agent['id']}",
                            extra={
                                "admin_user_id": str(admin_user_id),
                                "chatwoot_agent_id": agent["id"],
                            },
                        )
                return True

            return False

        elif action == "update":
            if not chatwoot_agent_id:
                logger.warning(
                    f"Cannot update Chatwoot agent without chatwoot_agent_id for admin_user_id={admin_user_id}",
                    extra={"admin_user_id": str(admin_user_id)},
                )
                return False

            result = await chatwoot.update_agent(
                agent_id=chatwoot_agent_id,
                name=display_name,
                email=email,
            )
            return result

        elif action == "delete":
            if not chatwoot_agent_id:
                logger.debug(
                    f"No chatwoot_agent_id to delete for admin_user_id={admin_user_id}",
                    extra={"admin_user_id": str(admin_user_id)},
                )
                return True

            result = await chatwoot.delete_agent(agent_id=chatwoot_agent_id)
            return result

        else:
            logger.error(
                f"Unknown action '{action}' for sync_agent_to_chatwoot",
                extra={"admin_user_id": str(admin_user_id), "action": action},
            )
            return False

    except Exception as e:
        logger.warning(
            f"Failed to sync agent admin_user_id={admin_user_id} to Chatwoot (action={action}): {e}",
            extra={"admin_user_id": str(admin_user_id), "action": action},
            exc_info=True,
        )
        return False


async def resync_agent_to_chatwoot(admin_user_id: uuid.UUID) -> dict[str, Any]:
    """
    Force re-sync an admin user to Chatwoot.
    Creates if no chatwoot_agent_id, updates if already linked.

    Returns: {"success": bool, "action": str, "chatwoot_agent_id": int|null, "error": str|null}
    """
    from database.connection import get_async_session
    from database.models import AdminUser

    async with get_async_session() as session:
        admin_user = await session.get(AdminUser, admin_user_id)

        if not admin_user:
            return {"success": False, "action": "", "chatwoot_agent_id": None, "error": "Admin user not found"}

        if admin_user.role != "agent":
            return {
                "success": False,
                "action": "",
                "chatwoot_agent_id": None,
                "error": "Chatwoot sync only applies to agent role",
            }

        if not admin_user.email:
            return {"success": False, "action": "", "chatwoot_agent_id": None, "error": "Cannot sync agent without email"}

        action = "update" if admin_user.chatwoot_agent_id else "create"

        result = await sync_agent_to_chatwoot(
            admin_user_id,
            action,
            display_name=admin_user.display_name,
            email=admin_user.email,
            chatwoot_agent_id=admin_user.chatwoot_agent_id,
        )

        if action == "create":
            await session.refresh(admin_user)

        return {
            "success": result,
            "action": action,
            "chatwoot_agent_id": admin_user.chatwoot_agent_id,
            "error": None if result else "Chatwoot sync failed",
        }
