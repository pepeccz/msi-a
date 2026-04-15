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
from shared.errors import ErrorCategory, get_error_logger

logger = logging.getLogger(__name__)
error_logger = get_error_logger()


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
        self.platform_token = settings.CHATWOOT_PLATFORM_TOKEN
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.inbox_id = settings.CHATWOOT_INBOX_ID
        self.image_send_delay_seconds = settings.CHATWOOT_IMAGE_SEND_DELAY_SECONDS

        self.headers = {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

        logger.info(
            f"ChatwootClient initialized: {self.api_url}, account_id={self.account_id}, "
            f"image_send_delay_seconds={self.image_send_delay_seconds}"
        )
    
    def _log_chatwoot_error(
        self,
        operation: str,
        customer_phone: str,
        error: Exception,
        *,
        exc_info: bool = True,
    ) -> None:
        """Log Chatwoot API errors with structured context.
        
        Args:
            operation: Description of the operation (e.g., "send message", "send template")
            customer_phone: Customer phone number
            error: Exception that occurred
            exc_info: Whether to include stack trace
        """
        error_logger.log_error(
            error=error,
            category=ErrorCategory.EXTERNAL_API_ERROR,
            context={
                "operation": operation,
                "customer_phone": customer_phone,
                "service": "chatwoot",
            },
            exc_info=exc_info,
        )

    @property
    def platform_headers(self) -> dict[str, str]:
        """Headers for Chatwoot Platform API (Bearer auth)."""
        return {
            "Authorization": f"Bearer {self.platform_token}",
            "Content-Type": "application/json",
        }

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
        email: str | None = None,
        custom_attributes: dict[str, Any] | None = None,
    ) -> bool:
        """
        Update a Chatwoot contact's name, email and/or custom attributes.

        Args:
            contact_id: Chatwoot contact ID
            name: Optional new name for the contact
            email: Optional email address for the contact
            custom_attributes: Optional dict of custom attributes to set

        Returns:
            True if update successful, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                payload: dict[str, Any] = {}

                if name is not None:
                    payload["name"] = name

                if email:  # Filters None and "" — never send empty email to Chatwoot
                    payload["email"] = email

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

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 422:
                    # 422 is a permanent validation error — no point retrying.
                    # Log the full response body to diagnose which field Chatwoot rejected.
                    logger.warning(
                        f"Chatwoot validation error (422) updating contact {contact_id} "
                        f"— not retrying. Response: {e.response.text}",
                    )
                    return False
                logger.error(
                    f"HTTP error updating contact {contact_id}: {e}",
                    exc_info=True,
                )
                raise
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
                contact = await self.find_contact_by_phone(customer_phone)
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
            self._log_chatwoot_error("send message", customer_phone, e)
            return False

        except Exception as e:
            self._log_chatwoot_error("send message", customer_phone, e)
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

            contact = await self.find_contact_by_phone(customer_phone)
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
            self._log_chatwoot_error("send template message", customer_phone, e)
            return False

        except Exception as e:
            self._log_chatwoot_error("send template message", customer_phone, e)
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

    @staticmethod
    def normalize_image_url(image_url: str) -> str:
        """Normalize relative image URLs to absolute using API_BASE_URL.

        Supported relative-path prefixes:
        - ``/images/...``      → element images uploaded via admin panel
        - ``/case-images/...`` → case/expediente images
        - ``/datos/Imagenes/...`` → legacy static image assets (SQL seed data)

        Any other relative path (starts with ``/``) is considered invalid
        and raises :class:`ValueError` so callers can log & skip.

        Absolute URLs (http/https) are returned unchanged.

        Args:
            image_url: Raw URL string from DB or tool output.

        Returns:
            Absolute URL suitable for HTTP download.

        Raises:
            ValueError: If the URL is a relative path with an unsupported prefix.
        """
        _KNOWN_RELATIVE_PREFIXES = ("/images/", "/case-images/", "/datos/Imagenes/")

        if image_url.startswith(("http://", "https://")):
            return image_url

        if any(image_url.startswith(prefix) for prefix in _KNOWN_RELATIVE_PREFIXES):
            settings = get_settings()
            return f"{settings.API_BASE_URL.rstrip('/')}{image_url}"

        # Relative path with unknown prefix → reject
        raise ValueError(
            f"Unsupported relative image path: {image_url!r}. "
            f"Expected one of: {', '.join(_KNOWN_RELATIVE_PREFIXES)}"
        )

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
    ) -> int | None:
        """
        Send an image to a conversation via Chatwoot.

        Downloads the image from the URL and uploads it as multipart/form-data
        since Chatwoot doesn't support external_url in attachments.

        Args:
            conversation_id: Chatwoot conversation ID
            image_url: Public URL of the image to send
            caption: Optional caption text to accompany the image

        Returns:
            The Chatwoot message ID if sent successfully, None otherwise.
            Note: callers using truthiness checks (if result:) remain compatible.
        """
        try:
            # Normalize relative image URLs to absolute via centralized method
            original_url = image_url
            try:
                image_url = self.normalize_image_url(image_url)
            except ValueError as exc:
                logger.error(
                    "image_url_normalization_failed",
                    extra={
                        "conversation_id": conversation_id,
                        "original_url": original_url,
                        "error": str(exc),
                        "error_code": "INVALID_IMAGE_URL",
                    },
                )
                return None

            if image_url != original_url:
                logger.debug(
                    f"Normalized relative image URL: {original_url} -> {image_url}",
                    extra={
                        "conversation_id": conversation_id,
                        "original_url": original_url,
                        "normalized_url": image_url,
                    },
                )
            
            logger.info(
                f"Sending image to conversation {conversation_id} | url={image_url}",
                extra={
                    "conversation_id": conversation_id,
                    "image_url": image_url,
                },
            )

            async with httpx.AsyncClient() as client:
                # Step 1: Download the image from URL
                logger.debug(f"Downloading image from {image_url}")
                img_response = await client.get(image_url, timeout=30.0)
                img_response.raise_for_status()

                # Extract filename and content type
                filename = image_url.split("/")[-1] or "image.png"
                content_type = img_response.headers.get("content-type", "image/png")
                file_content = img_response.content

                # Step 2: Upload to Chatwoot as multipart/form-data
                files = {
                    "attachments[]": (filename, file_content, content_type),
                }
                data = {
                    "content": caption or "",
                    "message_type": "outgoing",
                    "private": "false",
                }

                # Don't use json headers for multipart
                headers = {"api_access_token": self.api_token}

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                    data=data,
                    files=files,
                    headers=headers,
                    timeout=30.0,
                )

                # Log response body on error before raising
                if response.status_code >= 400:
                    logger.error(
                        f"Chatwoot error response: status={response.status_code} body={response.text}",
                        extra={"conversation_id": conversation_id},
                    )

                response.raise_for_status()

                # Parse response to get message_id for delivery tracking
                response_data = response.json()
                message_id = response_data.get("id")

                logger.info(
                    f"Image sent successfully to conversation {conversation_id} | message_id={message_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                    },
                )
                return message_id

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
            return None

    async def send_images(
        self,
        conversation_id: int,
        image_urls: list[str],
        captions: list[str | None] | None = None,
        caption_first: str | None = None,
    ) -> int:
        """
        Send multiple images to a conversation.

        Images are sent sequentially with a configurable delay between each to
        maintain order in the conversation.

        Args:
            conversation_id: Chatwoot conversation ID
            image_urls: List of public image URLs to send
            captions: Optional list of captions, one per image (NEW)
            caption_first: Optional caption for the first image only (DEPRECATED, use captions)

        Returns:
            Number of images successfully sent
        """
        if not image_urls:
            return 0

        sent_count = 0

        for i, image_url in enumerate(image_urls):
            try:
                # Extract caption for this image
                caption = None
                if captions and i < len(captions):
                    caption = captions[i]
                elif i == 0 and caption_first:
                    # Backward compatibility: caption_first for first image
                    caption = caption_first

                success = await self.send_image(
                    conversation_id=conversation_id,
                    image_url=image_url,
                    caption=caption,
                )

                if success:
                    sent_count += 1

                # Delay only in batched image sends to improve ordering consistency.
                if (
                    len(image_urls) > 1
                    and i < len(image_urls) - 1
                    and self.image_send_delay_seconds > 0
                ):
                    await asyncio.sleep(self.image_send_delay_seconds)

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def add_labels(
        self,
        conversation_id: int,
        labels: list[str],
    ) -> bool:
        """
        Add labels to a Chatwoot conversation.

        Labels help filter and categorize conversations in the Chatwoot UI.
        This method fetches current labels first and computes a set union so
        that existing labels are never replaced.

        Args:
            conversation_id: Chatwoot conversation ID
            labels: List of label names to add (e.g., ["escalado", "urgente"])

        Returns:
            True if labels added successfully (or already present), False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                # Fetch current labels to avoid replacing existing ones
                conversation = await self.get_conversation(conversation_id)
                current_labels: list[str] = conversation.get("labels", [])

                # Compute set union — new labels appended, duplicates dropped
                merged_labels: list[str] = list(set(current_labels) | set(labels))

                logger.debug(
                    "add_labels computed merge",
                    extra={
                        "conversation_id": conversation_id,
                        "current_labels": current_labels,
                        "new_labels": labels,
                        "merged_labels": merged_labels,
                    },
                )

                # Idempotency guard: nothing to do if the set is unchanged
                if set(merged_labels) == set(current_labels):
                    logger.debug(
                        "labels_already_present — skipping POST",
                        extra={
                            "conversation_id": conversation_id,
                            "labels": labels,
                        },
                    )
                    return True

                logger.info(
                    f"Adding labels {labels} to conversation {conversation_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "current_labels": current_labels,
                        "new_labels": labels,
                        "merged_labels": merged_labels,
                    },
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/labels",
                    json={"labels": merged_labels},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully added labels to conversation {conversation_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "current_labels": current_labels,
                        "new_labels": labels,
                        "merged_labels": merged_labels,
                    },
                )
                return True

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error adding labels to conversation {conversation_id}: {e}",
                    exc_info=True,
                )
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def add_private_note(
        self,
        conversation_id: int,
        note: str,
    ) -> bool:
        """
        Add a private note (internal comment) to a conversation.

        Private notes are only visible to agents, not customers.
        Useful for adding context during escalations.

        Args:
            conversation_id: Chatwoot conversation ID
            note: Note text to add

        Returns:
            True if note added successfully, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                logger.info(
                    f"Adding private note to conversation {conversation_id}"
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                    json={
                        "content": note,
                        "message_type": "outgoing",
                        "private": True,
                    },
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully added private note to conversation {conversation_id}",
                    extra={"conversation_id": conversation_id},
                )
                return True

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error adding private note to conversation {conversation_id}: {e}",
                    exc_info=True,
                )
                raise

    async def assign_to_team(
        self,
        conversation_id: int,
        team_id: int,
    ) -> bool:
        """
        Attempt to assign a conversation to a team.

        NOTE: This is best-effort and may fail if the bot token lacks
        permission to assign conversations. Failures are logged but
        do not raise exceptions.

        Args:
            conversation_id: Chatwoot conversation ID
            team_id: Team ID to assign to

        Returns:
            True if assignment successful, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                logger.info(
                    f"Attempting to assign conversation {conversation_id} to team {team_id}"
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/assignments",
                    json={"team_id": team_id},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully assigned conversation {conversation_id} to team {team_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "team_id": team_id,
                    },
                )
                return True

            except httpx.HTTPError as e:
                # Don't raise - this is best-effort
                logger.warning(
                    f"Could not assign conversation {conversation_id} to team {team_id}: {e}. "
                    "This is expected if bot token lacks assignment permissions.",
                    extra={
                        "conversation_id": conversation_id,
                        "team_id": team_id,
                    },
                )
                return False
            except Exception as e:
                logger.warning(
                    f"Unexpected error assigning conversation {conversation_id}: {e}",
                    extra={"conversation_id": conversation_id},
                )
                return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def get_conversation_messages(
        self,
        conversation_id: int,
        after: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get messages from a conversation, filtering to incoming image messages.

        Queries Chatwoot API for all messages in a conversation, filters to
        incoming messages (type=0) with image attachments created after the
        specified timestamp.

        Args:
            conversation_id: Chatwoot conversation ID
            after: Only return messages created after this unix timestamp

        Returns:
            List of message dicts containing image attachments
        """
        image_messages: list[dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            try:
                # Chatwoot messages API returns paginated results
                # We fetch all pages to ensure we don't miss any
                page = 1
                max_pages = 10  # Safety limit

                while page <= max_pages:
                    response = await client.get(
                        f"{self.api_url}/api/v1/accounts/{self.account_id}"
                        f"/conversations/{conversation_id}/messages",
                        headers=self.headers,
                        params={"page": page, "per_page": 100},
                        timeout=15.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    payload = data.get("payload", [])
                    if not payload:
                        break

                    for msg in payload:
                        # Only incoming messages (type 0 = from contact)
                        if msg.get("message_type") != 0:
                            continue
                        # Filter by timestamp if provided
                        if after and msg.get("created_at", 0) < after:
                            continue
                        # Only messages with image attachments
                        attachments = msg.get("attachments", [])
                        has_images = any(
                            a.get("file_type") == "image" for a in attachments
                        )
                        if has_images:
                            image_messages.append(msg)

                    # Check pagination
                    meta = data.get("meta", {})
                    total_pages = meta.get("pages", 1)
                    if page >= total_pages:
                        break
                    page += 1

                logger.info(
                    f"Fetched {len(image_messages)} image messages from conversation {conversation_id}",
                    extra={"conversation_id": conversation_id},
                )

            except httpx.HTTPError as e:
                logger.error(
                    f"Failed to fetch messages for conversation {conversation_id}: {e}",
                    exc_info=True,
                )
                raise

        return image_messages

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def get_conversation(
        self,
        conversation_id: int,
    ) -> dict[str, Any]:
        """
        Get conversation details including custom attributes.

        Args:
            conversation_id: Chatwoot conversation ID

        Returns:
            Conversation data including custom_attributes

        Raises:
            httpx.HTTPError: If Chatwoot API call fails
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}",
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                return cast(dict[str, Any], response.json())

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error getting conversation {conversation_id}: {e}",
                    exc_info=True,
                )
                raise

    async def remove_labels(
        self,
        conversation_id: int,
        labels: list[str],
    ) -> bool:
        """
        Remove labels from a Chatwoot conversation.

        Note: Chatwoot's label API replaces all labels. This method fetches
        current labels, removes the specified ones, and sets the result.

        Args:
            conversation_id: Chatwoot conversation ID
            labels: List of label names to remove

        Returns:
            True if labels removed successfully, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                # First, get current labels
                conversation = await self.get_conversation(conversation_id)
                current_labels = conversation.get("labels", [])

                # Remove specified labels
                new_labels = [l for l in current_labels if l not in labels]

                if new_labels == current_labels:
                    logger.debug(
                        f"No labels to remove from conversation {conversation_id}"
                    )
                    return True

                logger.info(
                    f"Removing labels {labels} from conversation {conversation_id}"
                )

                # Set new label list (Chatwoot replaces all labels)
                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/labels",
                    json={"labels": new_labels},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully removed labels from conversation {conversation_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "removed_labels": labels,
                        "remaining_labels": new_labels,
                    },
                )
                return True

            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error removing labels from conversation {conversation_id}: {e}",
                    exc_info=True,
                )
                return False
            except Exception as e:
                logger.warning(
                    f"Unexpected error removing labels from conversation {conversation_id}: {e}",
                    extra={"conversation_id": conversation_id},
                )
                return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def list_agents(self) -> list[dict[str, Any]]:
        """List all agents in the Chatwoot account."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/agents",
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                agents = response.json()
                logger.debug(f"Fetched {len(agents)} agents from account {self.account_id}")
                return cast(list[dict[str, Any]], agents)

            except httpx.HTTPError as e:
                logger.warning(f"HTTP error listing agents: {e}", exc_info=True)
                return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    async def create_platform_user(self, name: str, email: str, password: str) -> dict[str, Any] | None:
        """Create a user via Chatwoot Platform API. Returns user dict or None on 422."""
        if not self.platform_token:
            logger.warning("CHATWOOT_PLATFORM_TOKEN not configured — skipping platform user creation")
            return None

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/platform/api/v1/users",
                    json={"name": name, "email": email, "password": password},
                    headers=self.platform_headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                user = response.json()
                logger.info(f"Created platform user '{name}' with id={user.get('id')}")
                return cast(dict[str, Any], user)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 422:
                    logger.warning(f"Platform API validation error (422) creating user '{name}': {e.response.text}")
                    return None
                logger.error(f"HTTP error creating platform user '{name}': {e}", exc_info=True)
                raise
            except httpx.HTTPError as e:
                logger.error(f"HTTP error creating platform user '{name}': {e}", exc_info=True)
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    async def link_user_to_account(self, platform_user_id: int, role: str = "agent") -> bool:
        """Link a platform user to the Chatwoot account as an agent."""
        if not self.platform_token:
            logger.warning("CHATWOOT_PLATFORM_TOKEN not configured — skipping account link")
            return False

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/platform/api/v1/users/{platform_user_id}/account_users",
                    json={"account_id": int(self.account_id), "role": role},
                    headers=self.platform_headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info(f"Linked platform user {platform_user_id} to account {self.account_id} as {role}")
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 422:
                    logger.warning(f"Platform API error (422) linking user {platform_user_id}: {e.response.text}")
                    return False
                logger.error(f"HTTP error linking platform user {platform_user_id}: {e}", exc_info=True)
                raise
            except httpx.HTTPError as e:
                logger.error(f"HTTP error linking platform user {platform_user_id}: {e}", exc_info=True)
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    async def update_platform_user(self, platform_user_id: int, name: str | None = None, email: str | None = None, password: str | None = None) -> bool:
        """Update a platform user. Supports name, email, and password changes."""
        if not self.platform_token:
            logger.warning("CHATWOOT_PLATFORM_TOKEN not configured — skipping platform user update")
            return False

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if email is not None:
            payload["email"] = email
        if password is not None:
            payload["password"] = password

        if not payload:
            logger.debug(f"No updates to apply for platform user {platform_user_id}")
            return True

        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    f"{self.api_url}/platform/api/v1/users/{platform_user_id}",
                    json=payload,
                    headers=self.platform_headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info(f"Successfully updated platform user {platform_user_id}")
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (422, 404):
                    logger.warning(f"Platform API error ({e.response.status_code}) updating user {platform_user_id}: {e.response.text}")
                    return False
                logger.error(f"HTTP error updating platform user {platform_user_id}: {e}", exc_info=True)
                raise
            except httpx.HTTPError as e:
                logger.error(f"HTTP error updating platform user {platform_user_id}: {e}", exc_info=True)
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    async def delete_platform_user(self, platform_user_id: int) -> bool:
        """Delete a platform user from Chatwoot."""
        if not self.platform_token:
            logger.warning("CHATWOOT_PLATFORM_TOKEN not configured — skipping platform user deletion")
            return False

        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(
                    f"{self.api_url}/platform/api/v1/users/{platform_user_id}",
                    headers=self.platform_headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info(f"Successfully deleted platform user {platform_user_id}")
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.debug(f"Platform user {platform_user_id} not found (already deleted)")
                    return False
                logger.error(f"HTTP error deleting platform user {platform_user_id}: {e}", exc_info=True)
                raise
            except httpx.HTTPError as e:
                logger.error(f"HTTP error deleting platform user {platform_user_id}: {e}", exc_info=True)
                raise

    async def assign_conversation_to_agent(self, conversation_id: int, agent_id: int) -> bool:
        """Assign a conversation to a specific agent. Best-effort, no retry."""
        async with httpx.AsyncClient() as client:
            try:
                logger.info(
                    f"Attempting to assign conversation {conversation_id} to agent {agent_id}"
                )

                response = await client.post(
                    f"{self.api_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/assignments",
                    json={"assignee_id": agent_id},
                    headers=self.headers,
                    timeout=10.0,
                )
                response.raise_for_status()

                logger.info(
                    f"Successfully assigned conversation {conversation_id} to agent {agent_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "agent_id": agent_id,
                    },
                )
                return True

            except httpx.HTTPError as e:
                logger.warning(
                    f"Could not assign conversation {conversation_id} to agent {agent_id}: {e}",
                    extra={
                        "conversation_id": conversation_id,
                        "agent_id": agent_id,
                    },
                )
                return False
