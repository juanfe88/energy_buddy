"""Response generator sub-agent for sending confirmation messages via Twilio."""

import logging
import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from ...config import settings
from ...models import AgentState
from ...utils.retry import exponential_backoff_retry

# Configure logging
logger = logging.getLogger(__name__)


def format_success_message(date: str, measurement: float) -> str:
    """Format success confirmation message.
    
    Args:
        date: Date of the energy reading
        measurement: Measurement value
        
    Returns:
        Formatted success message string
        
    Requirements:
        - 4.1: Format confirmation message with date and measurement
    """
    return f"✅ Energy reading registered: {measurement} kWh on {date}"


def format_error_message() -> str:
    """Format error message.
    
    Returns:
        Formatted error message string
        
    Requirements:
        - 4.3: Send error message explaining failure reason
    """
    return "❌ Failed to register reading. Please try again."


@exponential_backoff_retry(
    max_retries=2,
    initial_delay=1.0,
    exceptions=(TwilioRestException,)
)
def send_whatsapp_with_retry(client: Client, from_whatsapp: str, to_whatsapp: str, message: str, media_url: str = None):
    """Send WhatsApp message with retry logic for transient errors.
    
    Args:
        client: Twilio client instance
        from_whatsapp: Sender WhatsApp number
        to_whatsapp: Recipient WhatsApp number
        message: Message content
        media_url: Optional URL or file path to media attachment
        
    Returns:
        Twilio message object
        
    Raises:
        TwilioRestException: If message sending fails after retries
    """
    try:
        # Build message parameters
        message_params = {
            "body": message,
            "from_": from_whatsapp,
            "to": to_whatsapp
        }
        
        # Add media URL if provided
        if media_url:
            message_params["media_url"] = [media_url]
        
        message_obj = client.messages.create(**message_params)
        return message_obj
    except TwilioRestException as e:
        # Only retry on transient errors (5xx server errors)
        if 500 <= e.status < 600:
            logger.warning(f"Transient Twilio error {e.status}: {e.msg}")
            raise
        else:
            # Don't retry on client errors (4xx)
            logger.error(f"Twilio client error {e.status}: {e.msg}")
            raise


def send_whatsapp_response(to_number: str, message: str, media_url: str = None) -> bool:
    """Send WhatsApp response via Twilio API with optional media attachment.
    
    Implements retry logic for transient errors and comprehensive error handling.
    
    Args:
        to_number: Recipient phone number
        message: Message content to send
        media_url: Optional URL or file path to media attachment (for MMS)
        
    Returns:
        True if message sent successfully, False otherwise
        
    Requirements:
        - 4.2: Send confirmation message through Twilio API
        - 4.4: Complete message sending within 5 seconds
        - 7.4: Send query response as text message
        - 10.4: Send plot as MMS attachment
    """
    if not to_number:
        logger.error("Cannot send WhatsApp message: to_number is empty")
        return False
    
    if not message:
        logger.error("Cannot send WhatsApp message: message is empty")
        return False
    
    try:
        # Initialize Twilio client
        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            return False
        
        # Format numbers for WhatsApp (must include whatsapp: prefix)
        from_whatsapp = f"whatsapp:{settings.twilio_phone_number}"
        to_whatsapp = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
        
        # Send WhatsApp message with retry logic
        if media_url:
            logger.info(f"Sending WhatsApp MMS to {to_whatsapp} with media: {media_url}")
        else:
            logger.info(f"Sending WhatsApp message to {to_whatsapp}")
        
        message_obj = send_whatsapp_with_retry(client, from_whatsapp, to_whatsapp, message, media_url)
        
        logger.info(f"WhatsApp message sent successfully. SID: {message_obj.sid}")
        return True
        
    except TwilioRestException as e:
        logger.error(f"Twilio API error after retries: {e.code} - {e.msg}")
        if e.code == 21211:
            logger.error("Invalid 'To' phone number format")
        elif e.code == 21606:
            logger.error("The 'From' phone number is not a valid WhatsApp-enabled number")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp message: {e}", exc_info=True)
        return False


def generate_response(state: AgentState) -> dict:
    """Node function to generate and send response message.
    
    This node formats a success or error message based on the bigquery_success
    flag or query_response, then sends it back to the user via Twilio WhatsApp.
    The response includes the extracted date and measurement on success, or the
    query agent's response for queries. If a plot was generated, it's sent as MMS.
    
    Args:
        state: Current agent state containing bigquery_success, extracted_date,
               extracted_measurement, query_response, plot_path, and from_number
        
    Returns:
        Dictionary with updated state field:
        - response_message: The message that was sent to the user
        
    Requirements:
        - 4.1: Format confirmation message containing date and measurement
        - 4.2: Send confirmation message through Twilio API
        - 4.3: Send error message explaining failure reason
        - 4.4: Complete message sending within 5 seconds
        - 7.4: Send query response as text message
        - 10.4: Send plot as MMS attachment and clean up temporary files
    """
    from_number = state.get("from_number")
    query_response = state.get("query_response")
    plot_path = state.get("plot_path")
    
    # Check if this is a query response
    if query_response:
        message = query_response
        media_url = None
        
        # If a plot was generated, prepare it for MMS
        if plot_path and os.path.exists(plot_path):
            logger.info(f"Plot file found at {plot_path}, will send as MMS")
            
            base_url = state.get("base_url")
            if base_url:
                # Construct public URL using the base URL (ngrok)
                # plot_path is like "static/plots/filename.png"
                filename = os.path.basename(plot_path)
                media_url = f"{base_url}/static/plots/{filename}"
                logger.info(f"Generated media URL: {media_url}")
            else:
                logger.warning("No base_url in state, cannot construct media URL for plot")
        
        # Send query response
        if from_number:
            send_success = send_whatsapp_response(from_number, message, media_url)
            if not send_success:
                logger.warning("Failed to send query response, but continuing workflow")
        else:
            logger.warning("No from_number in state, cannot send response")
        
        return {"response_message": message}
    
    # Handle energy counter reading responses
    is_energy_counter = state.get("is_energy_counter", False)
    bigquery_success = state.get("bigquery_success", False)
    
    # Format message based on success/failure
    if is_energy_counter:
        if bigquery_success:
            extracted_date = state.get("extracted_date", "unknown")
            extracted_measurement = state.get("extracted_measurement", 0.0)
            message = format_success_message(extracted_date, extracted_measurement)
        else:
            message = format_error_message()
    else:
        message = "Sorry Currently I can only register counter images from today... More functionalities comming."
    
    # Send WhatsApp response
    if from_number:
        send_success = send_whatsapp_response(from_number, message)
        if not send_success:
            logger.warning("Failed to send WhatsApp response, but continuing workflow")
    else:
        logger.warning("No from_number in state, cannot send response")
    
    return {"response_message": message}
