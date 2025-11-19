"""Interactive query agent for answering user questions about energy consumption.

This module implements a LangGraph ReAct agent that uses Gemini to answer
user questions about their energy consumption using available tools.
"""

import logging
from typing import Dict, Any
from langchain_google_vertexai import ChatVertexAI
from langgraph.prebuilt import create_react_agent
from google.api_core import exceptions as google_exceptions

from ...models import AgentState
from ...config import settings
from ...utils.retry import exponential_backoff_retry
from .tools.query_readings import query_readings
from .tools.price_tool import get_electricity_price
from .tools.plot_tool import generate_plot

# Configure logging
logger = logging.getLogger(__name__)

# System prompt for the query agent
SYSTEM_PROMPT = """You are an energy consumption assistant. Help users understand their electricity usage and costs.
You have access to tools to query their historical readings, get current electricity prices in France,
and generate visualizations. Be concise and helpful in your responses.

When users ask about their consumption:
- Use query_readings to fetch their historical data
- Use get_electricity_price to get current pricing information
- Use generate_plot to create visualizations when appropriate

Always provide clear, actionable insights based on the data."""


@exponential_backoff_retry(
    max_retries=3,
    initial_delay=1.0,
    exceptions=(google_exceptions.GoogleAPIError, google_exceptions.RetryError)
)
def invoke_query_agent_with_retry(agent, message: str) -> Dict[str, Any]:
    """Invoke the query agent with retry logic for API failures.
    
    Args:
        agent: The compiled LangGraph agent
        message: User's query message
        
    Returns:
        Agent response dictionary
        
    Raises:
        google_exceptions.GoogleAPIError: If API call fails after retries
    """
    try:
        logger.info(f"Invoking query agent with message: {message[:100]}...")
        response = agent.invoke(
            {"messages": [("user", message)]},
            config={"recursion_limit": 10}
        )
        return response
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Google API error during query agent invocation: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error invoking query agent: {e}")
        raise


def create_query_agent():
    """Create the interactive query agent with tools.
    
    This function initializes the ChatVertexAI model with Gemini,
    binds the three tools (query_readings, get_electricity_price, generate_plot),
    and creates a ReAct agent using LangGraph's prebuilt function.
    
    Returns:
        Compiled LangGraph agent ready for invocation
        
    Requirements:
        - 7.1: Analyze message content to determine if it's a consumption query
        - 7.2: Process questions using available tools
        - 7.3: Use Interactive Query Agent for text-only queries
    """
    try:
        # Initialize ChatVertexAI with Gemini
        # Uses Application Default Credentials automatically
        llm = ChatVertexAI(
            model="gemini-2.5-flash",
            project=settings.google_cloud_project,
            location=settings.vertex_ai_location,
            temperature=0.3,  # Balanced between creativity and accuracy
        )
        
        # Define available tools
        tools = [
            query_readings,
            get_electricity_price,
            generate_plot
        ]
        
        # Create ReAct agent with tools
        logger.info("Creating query agent with tools: query_readings, get_electricity_price, generate_plot")
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=SYSTEM_PROMPT
        )
        
        return agent
        
    except Exception as e:
        logger.error(f"Failed to create query agent: {e}", exc_info=True)
        raise


def handle_query(state: AgentState) -> Dict[str, Any]:
    """Handle user query by invoking the interactive query agent.
    
    This function creates the query agent, invokes it with the user's message,
    extracts the response, and checks if a plot was generated. It updates the
    AgentState with the query response and plot path if available.
    
    Args:
        state: Current agent state containing message_body
        
    Returns:
        Dictionary with updated state fields:
        - query_response: The agent's text response to the user's question
        - plot_path: Path to generated plot file if created, otherwise None
        
    Requirements:
        - 7.1: Analyze message content to determine if it's a consumption query
        - 7.2: Process questions using available tools
        - 7.3: Use Interactive Query Agent for text-only queries
        - 7.4: Send answer back through Twilio API within 15 seconds
    """
    query_response = None
    plot_path = None
    
    message_body = state.get("message_body", "")
    
    if not message_body:
        logger.warning("No message body found in state")
        return {
            "query_response": "I didn't receive a question. Please ask me about your energy consumption.",
            "plot_path": plot_path
        }
    
    try:
        # Create the query agent
        agent = create_query_agent()
        
        # Invoke agent with retry logic
        response = invoke_query_agent_with_retry(agent, message_body)
        
        # Extract the final response message
        messages = response.get("messages", [])
        if messages:
            # Get the last message (agent's final response)
            last_message = messages[-1]
            query_response = last_message.content
            logger.info(f"Query agent response: {query_response[:200]}...")
        else:
            logger.warning("No messages in agent response")
            query_response = "I couldn't process your question. Please try again."
        
        # Check if a plot was generated by examining tool calls
        # The plot tool returns a file path string
        for message in messages:
            # Check if this is a tool message with plot path
            if hasattr(message, 'content') and isinstance(message.content, str):
                # Check if content looks like a file path to a plot
                if '/energy_plot_' in message.content and message.content.endswith('.png'):
                    plot_path = message.content
                    logger.info(f"Plot generated at: {plot_path}")
                    break
        
    except google_exceptions.GoogleAPIError as e:
        # API error after retries
        logger.error(f"Vertex AI API error during query handling after retries: {e}")
        query_response = "I'm having trouble connecting to my AI service. Please try again in a moment."
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error during query handling: {e}", exc_info=True)
        query_response = "An unexpected error occurred while processing your question. Please try again."
    
    return {
        "query_response": query_response,
        "plot_path": plot_path
    }
