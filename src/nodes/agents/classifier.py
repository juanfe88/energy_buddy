"""Image classifier node for identifying energy counter images."""

import logging
import os
import tempfile
from typing import Dict, Any
import requests
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from google.api_core import exceptions as google_exceptions

from ...models import AgentState
from ...config import settings
from ...utils.retry import exponential_backoff_retry
from ...services.llm_factory import get_vision_model

# Configure logging
logger = logging.getLogger(__name__)


@exponential_backoff_retry(
    max_retries=2,
    initial_delay=0.5,
    exceptions=(requests.RequestException, IOError)
)
def download_and_save_image(media_url: str, message_sid: str) -> str:
    """Download image from Twilio media URL and save to temporary file.
    
    Args:
        media_url: URL to the media file from Twilio
        message_sid: Message SID for unique filename
        
    Returns:
        Path to saved image file
        
    Raises:
        requests.RequestException: If image download fails after retries
        IOError: If file save operation fails
    """
    try:
        # Use basic auth with Twilio credentials
        session = requests.Session()
        session.auth = (settings.twilio_account_sid, settings.twilio_auth_token)
        response = session.get(media_url, timeout=10)
        response.raise_for_status()
        
        # Save to temp directory with message_sid as filename
        temp_dir = tempfile.gettempdir()
        image_path =  f"{message_sid}.jpg"
        
        with open(image_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Saved image to: {image_path}")
        return image_path
    except requests.Timeout as e:
        logger.error(f"Timeout downloading image from {media_url}: {e}")
        raise
    except requests.RequestException as e:
        logger.error(f"Request error downloading image from {media_url}: {e}")
        raise
    except IOError as e:
        logger.error(f"IO error saving image to {image_path}: {e}")
        raise



def classify_image(state: AgentState) -> Dict[str, Any]:
    """Classify if the image contains an energy counter using Gemini Vision via Vertex AI.
    
    This function downloads the image from the Twilio media URL, saves it temporarily,
    and uses LangChain's ChatVertexAI with Gemini Vision to determine if it shows 
    an energy/electricity meter. Uses Application Default Credentials.
    Implements comprehensive error handling and retry logic for robustness.
    
    Args:
        state: Current agent state containing media URLs
        
    Returns:
        Dictionary with updated state fields:
        - is_energy_counter: Boolean indicating if image shows energy counter
        - image_path: Path to downloaded image for use by extractor
        
    Requirements:
        - 2.1: Download image from Twilio media URL
        - 2.2: Use Gemini vision to determine if image contains energy counter
        - 2.4: Handle image download failures gracefully
    """
    is_energy_counter = False
    image_path = None
    
    # Check if we have media URLs
    if not state.get("media_urls") or len(state["media_urls"]) == 0:
        logger.warning("No media URLs found in state")
        return {
            "is_energy_counter": is_energy_counter,
            "image_path": image_path
        }
    
    media_url = state["media_urls"][0]  # Process first image
    message_sid = state["message_sid"]
    
    try:
        # Download and save the image (with retry logic)
        logger.info(f"Downloading image from: {media_url}")
        image_path = download_and_save_image(media_url, message_sid)
        
        # Read image as base64 for API call
        import base64
        try:
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        except IOError as e:
            logger.error(f"Failed to read image file {image_path}: {e}")
            raise
        
        llm = get_vision_model()
        
        # Classification prompt with image
        prompt = "Is this an image of an energy/electricity meter or counter display? Answer yes or no."
        
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "base64": image_base64,
                    "mime_type": "image/jpeg",
                },
            ]
        )
        response_text = llm.invoke([message])
        response_text = response_text.content.strip().lower()
        logger.info(f"Gemini classification response: {response_text}")
        
        # Determine if it's an energy counter
        is_energy_counter = "yes" in response_text
        
    except requests.RequestException as e:
        # Non-critical error: image download failed
        logger.error(f"Failed to download image from {media_url} after retries: {e}")
        logger.info("Workflow will continue without image classification")
        # Clean up image if it was saved
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup image {image_path}: {cleanup_error}")
            image_path = None
    except google_exceptions.GoogleAPIError as e:
        # Non-critical error: API call failed
        logger.error(f"Vertex AI API error during classification after retries: {e}")
        logger.info("Workflow will continue without image classification")
        # Clean up image if it was saved
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup image {image_path}: {cleanup_error}")
            image_path = None
    except Exception as e:
        # Non-critical error: unexpected failure
        logger.error(f"Unexpected error during image classification: {e}", exc_info=True)
        logger.info("Workflow will continue without image classification")
        # Clean up image if it was saved
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup image {image_path}: {cleanup_error}")
            image_path = None
    
    return {
        "is_energy_counter": is_energy_counter,
        "image_path": image_path
    }
