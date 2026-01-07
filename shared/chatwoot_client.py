"""
Chatwoot client for sending messages and managing conversations.

This module provides the ChatwootClient class for interacting with the
Chatwoot API, including sending WhatsApp messages and updating conversation
attributes.
"""

import asyncio
import logging
from typing import Any, cast

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import get_settings

logger = logging.getLogger(__name__)


class ChatwootClient:
    """
    Client for interacting with Chatwoot API.

    This client handles finding or creating contacts/conversations and
    sending messages via the Chatwoot API.
    """

    def __init__(self):
        """Initialize Chatwoot client with credentials from settings."""
        settings = get_settings()
        self.api_url = settings.CHATWOOT_API_URL.rstrip("/")
        self.api_token = settings.CHATWOOT_API_TOKEN
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.inbox_id = settings.CHATWOOT_INBOX_ID

        self.headers = {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

        logger.info(f"ChatwootClient initialized: {self.api_url}, account_id={self.account_id}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def find_contact_by_phone(self, phone: str) -> dict[str, Any] | None:
        """
        Find Chatwoot contact by phone number.

        Args:
            phone: E.164 formatted phone number

        Returns:
            Contact dict if found, None otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/contacts/search",
                    params={"q": phone},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                payload = response.json().get("payload", [])
                if payload and len(payload) > 0:
                    logger.debug(f"Contact found for phone {phone}")
                    return cast(dict[str, Any], payload[0])

                logger.debug(f"No contact found for phone {phone}")
                return None

            except httpx.HTTPError as e:
                logger.error(f"HTTP error finding contact: {e}")
                raise

    # Alias for backward compatibility
    _find_contact_by_phone = find_contact_by_phone

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def update_contact(
        self,
        contact_id: int,
        name: str | None = None,
        custom_attributes: dict[str, Any] | None = None,
    ) -> bool:
        """
        Update a Chatwoot contact's name and/or custom attributes.

        Args:
            contact_id: Chatwoot contact ID
            name: Optional new name for the contact
            custom_attributes: Optional dict of custom attributes to set

        Returns:
            True if update successful, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                payload: dict[str, Any] = {}

                if name is not None:
                    payload["name"] = name

                if custom_attributes is not None:
                    payload["custom_attributes"] = custom_attributes

                if not payload:
                    logger.debug(f"No updates to apply for contact {contact_id}")
                    return True

                logger.info(
                    f"Updating contact {contact_id}: {payload}"
                )

                response = await client.put(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/contacts/{contact_id}",
                    json=payload,
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(f"Successfully updated contact {contact_id}")
                return True

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error updating contact {contact_id}: {e}",
                    exc_info=True,
                )
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def _create_contact(self, phone: str, name: str | None = None) -> dict[str, Any]:
        """
        Create new Chatwoot contact.

        Args:
            phone: E.164 formatted phone number
            name: Optional contact name

        Returns:
            Created contact dict
        """
        async with httpx.AsyncClient() as client:
            try:
                payload = {
                    "inbox_id": self.inbox_id,
                    "phone_number": phone,
                }
                if name:
                    payload["name"] = name

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/contacts",
                    json=payload,
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                contact = response.json().get("payload", {}).get("contact", {})
                logger.info(f"Created contact for phone {phone}, contact_id={contact.get('id')}")
                return cast(dict[str, Any], contact)

            except httpx.HTTPError as e:
                logger.error(f"HTTP error creating contact: {e}")
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def _get_or_create_conversation(self, contact_id: int) -> int:
        """
        Get existing conversation or create new one for contact.

        Args:
            contact_id: Chatwoot contact ID

        Returns:
            Conversation ID
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/contacts/{contact_id}",
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                contact = response.json().get("payload", {})

                contact_inboxes = contact.get("contact_inboxes", [])
                if not contact_inboxes:
                    logger.error(f"No contact_inboxes found for contact {contact_id}")
                    raise ValueError(f"Contact {contact_id} has no associated inboxes")

                source_id = contact_inboxes[0].get("source_id")
                logger.debug(f"Using source_id={source_id} from contact {contact_id}")

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations",
                    json={
                        "source_id": source_id,
                        "inbox_id": self.inbox_id,
                        "contact_id": contact_id,
                        "status": "open",
                    },
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                conversation_id = cast(int, response.json().get("id"))
                logger.info(f"Created conversation {conversation_id} for contact {contact_id}")
                return conversation_id

            except httpx.HTTPError as e:
                logger.error(f"HTTP error managing conversation: {e}")
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def update_conversation_attributes(
        self,
        conversation_id: int,
        attributes: dict[str, Any],
    ) -> bool:
        """
        Update custom attributes for a Chatwoot conversation.

        Args:
            conversation_id: Chatwoot conversation ID
            attributes: Dict of custom attributes to set

        Returns:
            True if update successful, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                logger.info(
                    f"Updating conversation {conversation_id} custom_attributes: {attributes}"
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/custom_attributes",
                    json={"custom_attributes": attributes},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully updated conversation {conversation_id} custom_attributes"
                )
                return True

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error updating conversation {conversation_id} attributes: {e}",
                    exc_info=True,
                )
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def send_message(
        self,
        customer_phone: str,
        message: str,
        customer_name: str | None = None,
        conversation_id: int | None = None,
    ) -> bool:
        """
        Send message to customer via Chatwoot.

        This method handles the complete flow:
        1. If conversation_id provided, use it directly
        2. Otherwise: Find or create contact by phone
        3. Get or create conversation for contact
        4. Send message to conversation

        Args:
            customer_phone: E.164 formatted phone number
            message: Message text to send
            customer_name: Optional customer name
            conversation_id: Optional existing conversation ID

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            logger.info(f"Sending message to {customer_phone}")

            logger.debug(
                f"Message to send: '{message}'",
                extra={
                    "customer_phone": customer_phone,
                    "message_length": len(message) if message else 0,
                    "conversation_id": conversation_id,
                }
            )

            if conversation_id is not None:
                logger.info(f"Using existing conversation_id={conversation_id}")
            else:
                contact = await self._find_contact_by_phone(customer_phone)
                if not contact:
                    logger.info(f"Creating new contact for {customer_phone}")
                    contact = await self._create_contact(customer_phone, customer_name)

                contact_id = contact.get("id")
                if not contact_id:
                    logger.error(f"No contact ID found for {customer_phone}")
                    return False

                conversation_id = await self._get_or_create_conversation(contact_id)

            async with httpx.AsyncClient() as client:
                api_payload = {
                    "content": message,
                    "message_type": "outgoing",
                    "private": False,
                }

                logger.debug(
                    f"Chatwoot API payload: {api_payload}",
                    extra={
                        "conversation_id": conversation_id,
                        "customer_phone": customer_phone,
                    }
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                    json=api_payload,
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.debug(
                    f"Chatwoot API response: status={response.status_code}",
                    extra={
                        "conversation_id": conversation_id,
                        "customer_phone": customer_phone,
                    }
                )

                logger.info(
                    f"Message sent successfully to {customer_phone}, conversation_id={conversation_id}"
                )
                return True

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to send message to {customer_phone} after retries: {e}",
                exc_info=True,
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error sending message to {customer_phone}: {e}",
                exc_info=True,
            )
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def send_template_message(
        self,
        customer_phone: str,
        template_name: str,
        body_params: dict[str, str],
        category: str = "UTILITY",
        language: str = "es",
        customer_name: str | None = None,
        conversation_id: int | None = None,
        fallback_content: str | None = None,
    ) -> bool:
        """
        Send WhatsApp template message via Chatwoot API.

        Template messages are required for sending messages outside the 24-hour
        conversation window.

        Args:
            customer_phone: E.164 formatted phone number
            template_name: Name of the approved template
            body_params: Dynamic variables for template body
            category: Template category (UTILITY, MARKETING, etc.)
            language: BCP 47 language code
            customer_name: Optional customer name
            conversation_id: Optional existing conversation ID
            fallback_content: Fallback text for non-WhatsApp channels

        Returns:
            True if template message sent successfully, False otherwise
        """
        try:
            logger.info(
                f"Sending template message to {customer_phone}, template={template_name}"
            )

            if conversation_id is not None:
                logger.info(f"Using existing conversation_id={conversation_id}")
                return await self._send_template_to_conversation(
                    conversation_id=conversation_id,
                    customer_phone=customer_phone,
                    template_name=template_name,
                    body_params=body_params,
                    category=category,
                    language=language,
                    fallback_content=fallback_content,
                )

            contact = await self._find_contact_by_phone(customer_phone)
            if not contact:
                logger.info(f"Creating new contact for {customer_phone}")
                contact = await self._create_contact(customer_phone, customer_name)

            contact_id = contact.get("id")
            if not contact_id:
                logger.error(f"No contact ID found for {customer_phone}")
                return False

            logger.info(
                f"Creating conversation with template for contact: "
                f"contact_id={contact_id}, phone={customer_phone}"
            )

            _, success = await self._create_conversation_with_template(
                contact_id=contact_id,
                phone=customer_phone,
                template_name=template_name,
                body_params=body_params,
                category=category,
                language=language,
                fallback_content=fallback_content,
            )
            return success

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to send template message to {customer_phone}: {e}",
                exc_info=True,
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error sending template message to {customer_phone}: {e}",
                exc_info=True,
            )
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def _create_conversation_with_template(
        self,
        contact_id: int,
        phone: str,
        template_name: str,
        body_params: dict[str, str],
        category: str = "UTILITY",
        language: str = "es",
        fallback_content: str | None = None,
    ) -> tuple[int, bool]:
        """Create a new conversation with an initial template message."""
        async with httpx.AsyncClient() as client:
            try:
                source_id = phone.lstrip("+")

                payload: dict[str, Any] = {
                    "source_id": source_id,
                    "inbox_id": int(self.inbox_id),
                    "contact_id": contact_id,
                    "status": "open",
                    "message": {
                        "content": fallback_content or f"Template: {template_name}",
                        "template_params": {
                            "name": template_name,
                            "category": category,
                            "language": language,
                            "processed_params": {
                                "body": body_params,
                            },
                        },
                    },
                }

                logger.debug(
                    f"Creating conversation with template for contact {contact_id}: {payload}"
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations",
                    json=payload,
                    headers=self.headers,
                    timeout=15.0,
                )
                response.raise_for_status()

                result = response.json()
                conversation_id = cast(int, result.get("id"))

                logger.info(
                    f"Created conversation {conversation_id} with template {template_name} "
                    f"for contact {contact_id}"
                )
                return (conversation_id, True)

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error creating conversation with template: {e}",
                    exc_info=True,
                )
                raise

    async def _send_template_to_conversation(
        self,
        conversation_id: int,
        customer_phone: str,
        template_name: str,
        body_params: dict[str, str],
        category: str = "UTILITY",
        language: str = "es",
        fallback_content: str | None = None,
    ) -> bool:
        """Send template message to an existing conversation."""
        api_payload: dict[str, Any] = {
            "content": fallback_content or f"Template: {template_name}",
            "message_type": "outgoing",
            "template_params": {
                "name": template_name,
                "category": category,
                "language": language,
                "processed_params": {
                    "body": body_params,
                },
            },
        }

        logger.debug(
            f"Chatwoot template API payload: {api_payload}",
            extra={
                "conversation_id": conversation_id,
                "customer_phone": customer_phone,
                "template_name": template_name,
            }
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                json=api_payload,
                headers=self.headers,
                timeout=15.0,
            )
            response.raise_for_status()

            logger.info(
                f"Template message sent successfully to {customer_phone}, "
                f"conversation_id={conversation_id}, template={template_name}"
            )
            return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def send_image(
        self,
        conversation_id: int,
        image_url: str,
        caption: str | None = None,
    ) -> bool:
        """
        Send an image to a conversation via Chatwoot.

        Uses the external URL attachment feature to send images without
        uploading them to Chatwoot storage.

        Args:
            conversation_id: Chatwoot conversation ID
            image_url: Public URL of the image to send
            caption: Optional caption text to accompany the image

        Returns:
            True if image sent successfully, False otherwise
        """
        try:
            logger.info(
                f"Sending image to conversation {conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "image_url": image_url[:100] + "..." if len(image_url) > 100 else image_url,
                },
            )

            async with httpx.AsyncClient() as client:
                # Chatwoot accepts attachments as external URLs via form data
                # or as direct URLs in the content with attachment type
                api_payload = {
                    "content": caption or "",
                    "message_type": "outgoing",
                    "private": False,
                    "attachments": [
                        {
                            "external_url": image_url,
                        }
                    ],
                }

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                    json=api_payload,
                    headers=self.headers,
                    timeout=15.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Image sent successfully to conversation {conversation_id}",
                    extra={"conversation_id": conversation_id},
                )
                return True

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to send image to conversation {conversation_id}: {e}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error sending image to conversation {conversation_id}: {e}",
                exc_info=True,
            )
            return False

    async def send_images(
        self,
        conversation_id: int,
        image_urls: list[str],
        caption_first: str | None = None,
    ) -> int:
        """
        Send multiple images to a conversation.

        Images are sent sequentially with a small delay between each to
        maintain order in the conversation.

        Args:
            conversation_id: Chatwoot conversation ID
            image_urls: List of public image URLs to send
            caption_first: Optional caption for the first image only

        Returns:
            Number of images successfully sent
        """
        if not image_urls:
            return 0

        sent_count = 0

        for i, image_url in enumerate(image_urls):
            try:
                # Only add caption to first image
                caption = caption_first if i == 0 else None

                success = await self.send_image(
                    conversation_id=conversation_id,
                    image_url=image_url,
                    caption=caption,
                )

                if success:
                    sent_count += 1

                # Small delay between images to maintain order
                if i < len(image_urls) - 1:
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(
                    f"Failed to send image {i + 1}/{len(image_urls)} to "
                    f"conversation {conversation_id}: {e}"
                )
                continue

        logger.info(
            f"Sent {sent_count}/{len(image_urls)} images to conversation {conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "total_images": len(image_urls),
                "sent_count": sent_count,
            },
        )

        return sent_count
