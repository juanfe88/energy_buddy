"""FastAPI application for Twilio Energy Monitor.

This module provides the main FastAPI application with endpoints for:
- Receiving Twilio webhook messages
- Health check monitoring
"""

import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from src.config import settings
from src.models import AgentState
from src.utils.twilio_utils import (
    verify_twilio_signature,
    extract_message_data
)
from src.workflow import invoke_workflow

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Twilio Energy Monitor",
    description="Backend service for processing energy counter readings via Twilio",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint.
    
    Returns a simple status response to verify the service is running.
    
    Returns:
        Dictionary with status message
        
    Requirements:
        - 1.4: Implement health endpoint
    """
    return {"status": "healthy", "service": "twilio-energy-monitor"}


@app.post("/webhook/twilio")
async def twilio_webhook(request: Request) -> Response:
    """Twilio webhook endpoint for receiving incoming messages.
    
    This endpoint receives webhook POST requests from Twilio, validates
    the signature, extracts message data, and invokes the LangGraph workflow
    to process the message.
    
    Args:
        request: FastAPI request object containing webhook data
        
    Returns:
        HTTP 200 response to acknowledge receipt to Twilio
        
    Raises:
        HTTPException: 403 if Twilio signature validation fails
        
    Requirements:
        - 1.1: Accept incoming request with valid Twilio signature verification
        - 1.2: Extract message content including text and media URLs
        - 1.3: Pass extracted message data to LangGraph Agent
        - 1.4: Return HTTP 200 status code within 10 seconds
    """
    try:
        
        # Get form data
        form_data = await request.form()
        form_dict = dict(form_data)
        # Get the full URL for signature validation
        scheme = request.headers.get('X-Forwarded-Proto', 'http') # Default to 'http' if header is absent
        print(request.headers)
        print(request.url)
        host = request.headers.get('X-Forwarded-Host') or request.headers.get('host')

        full_url = f"{scheme}://{host}/webhook/twilio"
        
        # Get Twilio signature from headers
        signature = request.headers.get("X-Twilio-Signature", "")
        
        # Verify Twilio signature
        if not verify_twilio_signature(
            url=full_url,
            post_data=form_dict,
            signature=signature,
            auth_token=settings.twilio_auth_token
        ):
            logger.warning(f"Invalid Twilio signature from {form_dict.get('From', 'unknown')}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature"
            )
        
        # Extract message data
        message_data = extract_message_data(form_dict)
        
        logger.info(f"Processing webhook for message {message_data['message_sid']}")
        
        # Create initial state for workflow
        initial_state: AgentState = {
            "message_sid": message_data["message_sid"],
            "from_number": message_data["from_number"],
            "message_body": message_data["message_body"],
            "media_urls": message_data["media_urls"],
            "has_image": False,  # Will be set by parser
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": "",
            "conversation": [HumanMessage(content=message_data["message_body"])],
            "base_url": f"{scheme}://{host}"
        }
        
        # Invoke LangGraph workflow
        # Note: This runs synchronously but should complete within Twilio's timeout
        final_state = invoke_workflow(initial_state, message_data["from_number"])
        
        logger.info(
            f"Workflow completed for message {message_data['message_sid']}: "
            f"bigquery_success={final_state.get('bigquery_success')}"
        )
        
        # Return 200 OK to Twilio
        return Response(status_code=status.HTTP_200_OK)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors but still return 200 to Twilio
        # to prevent retries for non-transient errors
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return Response(status_code=status.HTTP_200_OK)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
