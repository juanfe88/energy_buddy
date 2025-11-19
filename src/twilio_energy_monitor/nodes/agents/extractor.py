"""Reading extractor node for extracting energy counter measurements."""

import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime
import base64
from pydantic import BaseModel, Field
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from google.api_core import exceptions as google_exceptions

from ...models import AgentState
from ...config import settings
from ...utils.retry import exponential_backoff_retry

# Configure logging
logger = logging.getLogger(__name__)


class MeterReading(BaseModel):
    """Structured output model for meter reading extraction."""
    
    measurement: Optional[float] = Field(
        None,
        description="The current reading/measurement value from the energy meter"
    )


@exponential_backoff_retry(
    max_retries=3,
    initial_delay=1.0,
    exceptions=(google_exceptions.GoogleAPIError, google_exceptions.RetryError)
)
def call_gemini_vision_extraction(image_base64: str) -> MeterReading:
    """Call Gemini Vision API for reading extraction with retry logic.
    
    Args:
        image_base64: Base64-encoded image data
        
    Returns:
        MeterReading object with extracted measurement
        
    Raises:
        google_exceptions.GoogleAPIError: If API call fails after retries
    """
    try:
        # Initialize ChatVertexAI with Gemini Vision and structured output
        # Uses Application Default Credentials automatically
        llm = ChatVertexAI(
            model="gemini-2.5-flash-lite",
            project=settings.google_cloud_project,
            location=settings.vertex_ai_location,
            temperature=0.2,
        )
        
        # Use structured output with Pydantic model
        structured_llm = llm.with_structured_output(MeterReading)
        
        # Structured extraction prompt
        prompt = "Extract the current reading/measurement value from this energy meter."
        
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
        
        # Call Gemini Vision API via LangChain with structured output
        logger.info("Calling Vertex AI Gemini Vision API for extraction")
        result: MeterReading = structured_llm.invoke([message])
        
        return result
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Google API error during extraction: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling Gemini Vision API: {e}")
        raise


def extract_reading(state: AgentState) -> Dict[str, Any]:
    """Extract measurement from energy counter image using Gemini Vision.
    
    This function reads the previously downloaded image and uses LangChain's 
    ChatVertexAI with Gemini Vision to extract the measurement value.
    The date is set to the current timestamp. After extraction, the temporary
    image file is deleted. Uses Application Default Credentials for authentication.
    Implements comprehensive error handling and retry logic for robustness.
    
    Args:
        state: Current agent state containing image_path
        
    Returns:
        Dictionary with updated state fields:
        - extracted_date: Current timestamp in ISO format
        - extracted_measurement: Numeric measurement value (if found)
        
    Requirements:
        - 2.3: Extract measurement value and timestamp from energy counter image
    """
    extracted_date = None
    extracted_measurement = None
    image_path = state.get("image_path")
    
    # Check if we have an image path
    if not image_path or not os.path.exists(image_path):
        logger.warning("No valid image path found in state")
        return {
            "extracted_date": extracted_date,
            "extracted_measurement": extracted_measurement
        }
    
    try:
        # Read image as base64
        logger.info(f"Reading image from: {image_path}")
        try:
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        except IOError as e:
            logger.error(f"Failed to read image file {image_path}: {e}")
            raise
        
        # Call Gemini Vision API with retry logic
        result = call_gemini_vision_extraction(image_base64)
        logger.info(f"Gemini extraction result: {result}")
        
        # Extract measurement from structured output
        if result.measurement is not None:
            # Validate measurement is a valid number
            if isinstance(result.measurement, (int, float)) and result.measurement >= 0:
                extracted_measurement = result.measurement
                logger.info(f"Extracted measurement: {extracted_measurement}")
            else:
                logger.warning(f"Invalid measurement value: {result.measurement}")
        else:
            logger.warning("No measurement extracted from image")
        
        # Set date to current timestamp
        extracted_date = datetime.now().isoformat()
        logger.info(f"Using current timestamp: {extracted_date}")
        
    except google_exceptions.GoogleAPIError as e:
        # Non-critical error: API call failed
        logger.error(f"Vertex AI API error during extraction after retries: {e}")
        logger.info("Workflow will continue without extracted reading")
    except IOError as e:
        # Non-critical error: file read failed
        logger.error(f"IO error reading image file: {e}")
        logger.info("Workflow will continue without extracted reading")
    except Exception as e:
        # Non-critical error: unexpected failure
        logger.error(f"Unexpected error during reading extraction: {e}", exc_info=True)
        logger.info("Workflow will continue without extracted reading")
    finally:
        # Clean up temporary image file
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logger.info(f"Deleted temporary image: {image_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary image {image_path}: {e}")
    
    return {
        "extracted_date": extracted_date,
        "extracted_measurement": extracted_measurement
    }
