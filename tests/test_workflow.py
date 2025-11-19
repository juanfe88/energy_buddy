"""Integration tests for the LangGraph workflow."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.twilio_energy_monitor.models import AgentState
from twilio_energy_monitor.workflow import (
    invoke_workflow,
    should_classify_image,
    should_extract_reading
)


class TestWorkflowRouting:
    """Tests for workflow conditional routing logic."""
    
    def test_should_classify_image_with_image(self):
        """Test routing to classify_image when message has image."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/image.jpg"],
            "has_image": True,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = should_classify_image(state)
        
        assert result == "classify_image"
    
    def test_should_classify_image_without_image(self):
        """Test routing to end when message has no image."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Text only",
            "media_urls": [],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = should_classify_image(state)
        
        assert result == "end"
    
    def test_should_extract_reading_when_energy_counter(self):
        """Test routing to extract_reading when image is energy counter."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/meter.jpg"],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": "/tmp/test.jpg",
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = should_extract_reading(state)
        
        assert result == "extract_reading"
    
    def test_should_extract_reading_when_not_energy_counter(self):
        """Test routing to end when image is not energy counter."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/cat.jpg"],
            "has_image": True,
            "is_energy_counter": False,
            "image_path": "/tmp/test.jpg",
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = should_extract_reading(state)
        
        assert result == "end"


class TestWorkflowIntegration:
    """Integration tests for complete workflow execution."""
    
    @patch('src.twilio_energy_monitor.nodes.agents.responder.Client')
    @patch('src.twilio_energy_monitor.nodes.bigquery_writer.bigquery.Client')
    @patch('src.twilio_energy_monitor.nodes.agents.extractor.ChatVertexAI')
    @patch('src.twilio_energy_monitor.nodes.agents.extractor.os.path.exists')
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.ChatVertexAI')
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.requests.get')
    @patch('builtins.open', create=True)
    def test_complete_workflow_with_energy_counter(
        self,
        mock_open,
        mock_requests,
        mock_classifier_chat,
        mock_exists,
        mock_extractor_chat,
        mock_bq_client,
        mock_twilio_client
    ):
        """Test complete workflow with energy counter image."""
        # Mock image download
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_requests.return_value = mock_response
        
        # Mock file operations
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = b"fake_image"
        
        # Mock classifier Gemini response
        mock_classifier_llm = Mock()
        mock_classifier_result = Mock()
        mock_classifier_result.content = "yes"
        mock_classifier_llm.invoke.return_value = mock_classifier_result
        mock_classifier_chat.return_value = mock_classifier_llm
        
        # Mock extractor Gemini response
        mock_extractor_llm = Mock()
        mock_structured_llm = Mock()
        mock_extraction_result = Mock()
        mock_extraction_result.measurement = 12345.67
        mock_structured_llm.invoke.return_value = mock_extraction_result
        mock_extractor_llm.with_structured_output.return_value = mock_structured_llm
        mock_extractor_chat.return_value = mock_extractor_llm
        
        # Mock BigQuery client
        mock_bq = Mock()
        mock_bq.get_table.return_value = Mock()
        mock_query_job = Mock()
        mock_bq.query.return_value = mock_query_job
        mock_bq_client.return_value = mock_bq
        
        # Mock Twilio client
        mock_twilio = Mock()
        mock_message = Mock()
        mock_message.sid = "test_message_sid"
        mock_twilio.messages.create.return_value = mock_message
        mock_twilio_client.return_value = mock_twilio
        
        # Initial state
        initial_state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Here's my meter reading",
            "media_urls": ["https://example.com/meter.jpg"],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        # Invoke workflow
        final_state = invoke_workflow(initial_state)
        
        # Verify workflow completed successfully
        assert final_state["has_image"] is True
        assert final_state["is_energy_counter"] is True
        assert final_state["extracted_measurement"] == 12345.67
        assert final_state["bigquery_success"] is True
        assert "✅" in final_state["response_message"]
    
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.ChatVertexAI')
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.requests.get')
    def test_workflow_with_non_energy_counter_image(
        self,
        mock_requests,
        mock_classifier_chat
    ):
        """Test workflow with non-energy counter image (should end early)."""
        # Mock image download
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_requests.return_value = mock_response
        
        # Mock classifier Gemini response (not energy counter)
        mock_classifier_llm = Mock()
        mock_classifier_result = Mock()
        mock_classifier_result.content = "no"
        mock_classifier_llm.invoke.return_value = mock_classifier_result
        mock_classifier_chat.return_value = mock_classifier_llm
        
        # Initial state
        initial_state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Check out this cat",
            "media_urls": ["https://example.com/cat.jpg"],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        # Invoke workflow
        final_state = invoke_workflow(initial_state)
        
        # Verify workflow ended early
        assert final_state["has_image"] is True
        assert final_state["is_energy_counter"] is False
        assert final_state["extracted_measurement"] is None
        assert final_state["bigquery_success"] is False
    
    def test_workflow_with_no_image(self):
        """Test workflow with text-only message (should end immediately)."""
        # Initial state
        initial_state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Hello, just a text message",
            "media_urls": [],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        # Invoke workflow
        final_state = invoke_workflow(initial_state)
        
        # Verify workflow ended immediately
        assert final_state["has_image"] is False
        assert final_state["is_energy_counter"] is False
        assert final_state["extracted_measurement"] is None
        assert final_state["bigquery_success"] is False
