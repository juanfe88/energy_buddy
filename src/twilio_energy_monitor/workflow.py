"""LangGraph workflow orchestration for the Twilio Energy Monitor.

This module defines the workflow graph that orchestrates all sub-agents
for processing Twilio messages, classifying images, extracting readings,
writing to BigQuery, and generating responses.
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END

from .models import AgentState
from .nodes.parser import parse_message
from .nodes.agents.classifier import classify_image
from .nodes.agents.extractor import extract_reading
from .nodes.bigquery_writer import write_to_bigquery
from .nodes.agents.responder import generate_response
from .nodes.agents.query_agent import handle_query

# Configure logging
logger = logging.getLogger(__name__)


def should_classify_image(state: AgentState) -> Literal["classify_image", "query_handler", "responder"]:
    """Conditional edge function to determine routing after message parsing.
    
    Routes to classify_image if the message has an image, to query_handler if it's
    a text-only query, otherwise ends workflow.
    
    Args:
        state: Current agent state
        
    Returns:
        "classify_image" if has_image is True
        "query_handler" if is_query is True
        "responder" otherwise
        
    Requirements:
        - 5.2: Support conditional routing based on message content type
        - 7.1: Route text-only queries to query agent
    """
    has_image = state.get("has_image", False)
    is_query = state.get("is_query", False)
    logger.info(f"Routing decision: has_image={has_image}, is_query={is_query}")
    
    if has_image:
        return "classify_image"
    elif is_query:
        return "query_handler"
    return "responder"


def should_extract_reading(state: AgentState) -> Literal["extract_reading", "responder"]:
    """Conditional edge function to determine if reading extraction is needed.
    
    Routes to extract_reading if the image is an energy counter, otherwise ends workflow.
    
    Args:
        state: Current agent state
        
    Returns:
        "extract_reading" if is_energy_counter is True, "end" otherwise
        
    Requirements:
        - 5.2: Support conditional routing based on classification results
    """
    is_energy_counter = state.get("is_energy_counter", False)
    logger.info(f"Routing decision: is_energy_counter={is_energy_counter}")
    
    if is_energy_counter:
        return "extract_reading"
    return "responder"


def create_workflow() -> StateGraph:
    """Create and compile the LangGraph workflow.
    
    This function builds the complete workflow graph with all sub-agent nodes
    and conditional edges for routing based on message content and classification.
    
    Returns:
        Compiled StateGraph ready for execution
        
    Requirements:
        - 5.1: Define workflow graph with all sub-agent nodes
        - 5.2: Support conditional routing
        - 5.3: Provide modular architecture for adding new sub-agents
        - 5.4: Maintain state across workflow steps
        - 7.1: Route text-only queries to query agent
        - 7.3: Integrate query agent into workflow
    """
    # Initialize StateGraph with AgentState schema
    workflow = StateGraph(AgentState)
    
    # Add all sub-agent nodes
    workflow.add_node("parse_message", parse_message)
    workflow.add_node("classify_image", classify_image)
    workflow.add_node("extract_reading", extract_reading)
    workflow.add_node("write_to_bigquery", write_to_bigquery)
    workflow.add_node("query_handler", handle_query)
    workflow.add_node("generate_response", generate_response)
    
    # Set entry point
    workflow.set_entry_point("parse_message")
    
    # Define conditional edges
    # After parsing, check if message has image or is a query
    workflow.add_conditional_edges(
        "parse_message",
        should_classify_image,
        {
            "classify_image": "classify_image",
            "query_handler": "query_handler",
            "responder": "generate_response"
        }
    )
    
    # After classification, check if image is energy counter
    workflow.add_conditional_edges(
        "classify_image",
        should_extract_reading,
        {
            "extract_reading": "extract_reading",
            "responder": "generate_response"
        }
    )
    
    # After extraction, always write to BigQuery
    workflow.add_edge("extract_reading", "write_to_bigquery")
    
    # After BigQuery write, always generate response
    workflow.add_edge("write_to_bigquery", "generate_response")
    
    # After query handling, always generate response
    workflow.add_edge("query_handler", "generate_response")
    
    # After response generation, end workflow
    workflow.add_edge("generate_response", END)
    
    # Compile the graph
    logger.info("Compiling LangGraph workflow")
    compiled_workflow = workflow.compile()
    
    return compiled_workflow


def invoke_workflow(initial_state: AgentState) -> AgentState:
    """Invoke the workflow with initial state.
    
    This is the main entry point for executing the workflow. It creates
    the workflow graph and invokes it with the provided initial state.
    
    Args:
        initial_state: Initial agent state containing message data from Twilio webhook
        
    Returns:
        Final agent state after workflow execution
        
    Requirements:
        - 5.1: Export function to invoke workflow with initial state
        - 5.4: Maintain state across workflow steps
    """
    logger.info(f"Invoking workflow with message_sid={initial_state.get('message_sid')}")
    
    # Create workflow
    workflow = create_workflow()
    
    # Invoke workflow with initial state
    final_state = workflow.invoke(initial_state)
    
    logger.info(f"Workflow completed. Final state: bigquery_success={final_state.get('bigquery_success')}")
    
    return final_state
