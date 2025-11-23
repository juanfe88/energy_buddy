"""Message parser node for extracting data from Twilio webhooks."""

import logging
from typing import Dict, Any
from ..models import AgentState

# Configure logging
logger = logging.getLogger(__name__)


def parse_message(state: AgentState) -> Dict[str, Any]:
    """Parse incoming Twilio webhook payload and extract message data.
    
    This function extracts message metadata from the Twilio webhook payload
    and determines if the message contains images by checking for media URLs.
    For text-only messages, it sets the is_query flag to route to the query agent.
    Implements basic validation and error handling.
    
    Args:
        state: Current agent state containing the Twilio webhook data
        
    Returns:
        Dictionary with updated state fields:
        - has_image: Boolean flag indicating if message contains media
        - is_query: Boolean flag indicating if message is a text-only query
        
    Requirements:
        - 1.2: Extract message content including text and media URLs
        - 1.3: Pass extracted message data to LangGraph Agent
        - 7.1: Identify text-only queries for routing to query agent
    """
    try:
        # Validate state has required fields
        if not state:
            logger.error("Received empty state")
            return {"has_image": False, "is_query": False}
        
        # Log incoming message details
        message_sid = state.get("message_sid", "unknown")
        from_number = state.get("from_number", "unknown")
        message_body = state.get("message_body", "")
        logger.info(f"Parsing message {message_sid} from {from_number}")
        
        # Check if media URLs are present in the message
        media_urls = state.get("media_urls")
        has_image = bool(media_urls and len(media_urls) > 0)
        
        # Determine if this is a text-only query
        # A message is a query if it has text content but no images
        is_query = bool(message_body and not has_image)
        
        if has_image:
            logger.info(f"Message contains {len(media_urls)} media URL(s)")
        elif is_query:
            logger.info(f"Message is a text-only query: {message_body[:50]}...")
        else:
            logger.info("Message contains no media and no text")
        
        return {
            "has_image": has_image,
            "is_query": is_query,
            # Reset transient fields to prevent state persistence across turns
            "plot_path": None,
            "query_response": None,
            "bigquery_success": False,
            "extracted_date": None,
            "extracted_measurement": None,
            "image_path": None,
            "is_energy_counter": False
        }
        
    except Exception as e:
        # Non-critical error: parsing failed
        logger.error(f"Error parsing message: {e}", exc_info=True)
        logger.info("Workflow will continue with has_image=False and is_query=False")
        return {
            "has_image": False, 
            "is_query": False,
            # Reset transient fields even on error
            "plot_path": None,
            "query_response": None,
            "bigquery_success": False,
            "extracted_date": None,
            "extracted_measurement": None,
            "image_path": None,
            "is_energy_counter": False
        }
