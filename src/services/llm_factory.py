"""Factory service for providing shared LLM instances.

This module implements the Singleton/Factory pattern for LLM clients to ensure
efficient resource usage and consistent configuration across the application.
"""

import logging
from functools import lru_cache
from langchain_google_vertexai import ChatVertexAI
from ..config import settings

# Configure logging
logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_vision_model() -> ChatVertexAI:
    """Get a singleton instance of the Gemini Vision model.
    
    Returns:
        Configured ChatVertexAI instance for vision tasks
    """
    logger.info("Initializing Vision model")
    return ChatVertexAI(
        model="gemini-2.5-flash-lite",
        project=settings.google_cloud_project,
        location=settings.vertex_ai_location,
        temperature=0.1, 
    )

@lru_cache(maxsize=1)
def get_chat_model() -> ChatVertexAI:
    """Get a singleton instance of the Gemini Chat model.
    
    Returns:
        Configured ChatVertexAI instance for chat tasks
    """
    logger.info("Initializing Chat model")
    return ChatVertexAI(
        model="gemini-2.5-flash",
        project=settings.google_cloud_project,
        location=settings.vertex_ai_location,
        temperature=0.3, 
    )
