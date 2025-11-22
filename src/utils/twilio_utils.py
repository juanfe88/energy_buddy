"""Twilio utility functions for webhook validation and data extraction."""

import logging
from typing import Dict, Any
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)


def verify_twilio_signature(
    url: str,
    post_data: Dict[str, Any],
    signature: str,
    auth_token: str
) -> bool:
    """Verify that a request came from Twilio using signature validation.
    
    This function validates the X-Twilio-Signature header to ensure the
    webhook request is authentic and came from Twilio.
    
    Args:
        url: The full URL of the webhook endpoint (including protocol and domain)
        post_data: Dictionary of POST parameters from the request
        signature: The X-Twilio-Signature header value
        auth_token: Twilio auth token from configuration
        
    Returns:
        True if signature is valid, False otherwise
        
    Requirements:
        - 1.1: Accept incoming request with valid Twilio signature verification
    """
    try:
        validator = RequestValidator(auth_token)
        is_valid = validator.validate(url, post_data, signature)
        
        if not is_valid:
            logger.warning(f"Invalid Twilio signature for URL: {url}")
        
        return is_valid
    except Exception as e:
        logger.error(f"Error validating Twilio signature: {e}")
        return False


def extract_message_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant message data from Twilio webhook payload.
    
    Parses the Twilio webhook form data and extracts the fields needed
    for the LangGraph workflow.
    
    Args:
        form_data: Dictionary of form parameters from Twilio webhook
        
    Returns:
        Dictionary containing extracted message data with keys:
        - message_sid: Unique message identifier
        - from_number: Sender's phone number
        - message_body: Text content of the message
        - media_urls: List of media URLs (images, videos, etc.)
        
    Requirements:
        - 1.2: Extract message content including text and media URLs from webhook payload
    """
    # Extract basic message fields
    message_sid = form_data.get("MessageSid", "")
    from_number = form_data.get("From", "")
    message_body = form_data.get("Body", "")
    
    # Extract media URLs
    num_media = int(form_data.get("NumMedia", 0))
    media_urls = []
    
    for i in range(num_media):
        media_url = form_data.get(f"MediaUrl{i}")
        if media_url:
            media_urls.append(media_url)
    
    logger.info(
        f"Extracted message data: sid={message_sid}, from={from_number}, "
        f"body_length={len(message_body)}, num_media={len(media_urls)}"
    )
    
    return {
        "message_sid": message_sid,
        "from_number": from_number,
        "message_body": message_body,
        "media_urls": media_urls
    }
