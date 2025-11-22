"""Data models for the Twilio Energy Monitor application."""

from typing import List, Optional, TypedDict,Annotated
from operator import add
from langchain_core.messages import BaseMessage



class AgentState(TypedDict):
    """State schema for the LangGraph workflow.
    
    This TypedDict defines all state fields that are passed between
    sub-agents in the workflow orchestration.
    """
    message_sid: str
    from_number: str
    message_body: str
    media_urls: List[str]
    has_image: bool
    is_query: bool  # Flag indicating if message is a text-only query
    is_energy_counter: bool
    image_path: Optional[str]  # Temporary path to downloaded image
    extracted_date: Optional[str]
    extracted_measurement: Optional[float]
    bigquery_success: bool
    query_response: Optional[str]  # Response from interactive query agent
    plot_path: Optional[str]  # Path to generated plot file
    conversation: Annotated[List[BaseMessage],add]
    response_message: str
    base_url: str
