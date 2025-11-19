"""Unit tests for sub-agent functions."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.twilio_energy_monitor.models import AgentState
from src.twilio_energy_monitor.nodes.parser import parse_message
from src.twilio_energy_monitor.nodes.agents.classifier import classify_image
from src.twilio_energy_monitor.nodes.agents.extractor import extract_reading
from src.twilio_energy_monitor.nodes.bigquery_writer import write_to_bigquery
from src.twilio_energy_monitor.nodes.agents.responder import (
    generate_response,
    format_success_message,
    format_error_message
)


class TestParseMessage:
    """Tests for the message parser sub-agent."""
    
    def test_parse_message_with_media(self):
        """Test parsing message with media URLs."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Test message",
            "media_urls": ["https://example.com/image.jpg"],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = parse_message(state)
        
        assert result["has_image"] is True
    
    def test_parse_message_without_media(self):
        """Test parsing message without media URLs."""
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Test message",
            "media_urls": [],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = parse_message(state)
        
        assert result["has_image"] is False


class TestClassifyImage:
    """Tests for the image classifier sub-agent."""
    
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.requests.get')
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.ChatVertexAI')
    def test_classify_image_as_energy_counter(self, mock_chat, mock_requests):
        """Test classifying image as energy counter."""
        # Mock image download
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_requests.return_value = mock_response
        
        # Mock Gemini response
        mock_llm = Mock()
        mock_result = Mock()
        mock_result.content = "yes"
        mock_llm.invoke.return_value = mock_result
        mock_chat.return_value = mock_llm
        
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/meter.jpg"],
            "has_image": True,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = classify_image(state)
        
        assert result["is_energy_counter"] is True
        assert result["image_path"] is not None
    
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.requests.get')
    @patch('src.twilio_energy_monitor.nodes.agents.classifier.ChatVertexAI')
    def test_classify_image_not_energy_counter(self, mock_chat, mock_requests):
        """Test classifying image as not energy counter."""
        # Mock image download
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_requests.return_value = mock_response
        
        # Mock Gemini response
        mock_llm = Mock()
        mock_result = Mock()
        mock_result.content = "no"
        mock_llm.invoke.return_value = mock_result
        mock_chat.return_value = mock_llm
        
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/cat.jpg"],
            "has_image": True,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = classify_image(state)
        
        assert result["is_energy_counter"] is False


class TestExtractReading:
    """Tests for the reading extractor sub-agent."""
    
    @patch('src.twilio_energy_monitor.nodes.agents.extractor.ChatVertexAI')
    @patch('src.twilio_energy_monitor.nodes.agents.extractor.os.path.exists')
    @patch('builtins.open', create=True)
    def test_extract_reading_success(self, mock_open, mock_exists, mock_chat):
        """Test successful reading extraction."""
        # Mock file operations
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = b"fake_image"
        
        # Mock Gemini response with structured output
        mock_llm = Mock()
        mock_structured_llm = Mock()
        mock_result = Mock()
        mock_result.measurement = 12345.67
        mock_structured_llm.invoke.return_value = mock_result
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_chat.return_value = mock_llm
        
        state: AgentState = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": ["https://example.com/meter.jpg"],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": "/tmp/test_image.jpg",
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = extract_reading(state)
        
        assert result["extracted_measurement"] == 12345.67
        assert result["extracted_date"] is not None


class TestBigQueryWriter:
    """Tests for the BigQuery writer sub-agent."""
    
    @patch('src.twilio_energy_monitor.nodes.bigquery_writer.bigquery.Client')
    def test_write_to_bigquery_success(self, mock_client):
        """Test successful BigQuery write."""
        # Mock BigQuery client
        mock_bq = Mock()
        mock_bq.get_table.return_value = Mock()  # Table exists
        mock_query_job = Mock()
        mock_bq.query.return_value = mock_query_job
        mock_client.return_value = mock_bq
        
        state = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": [],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": None,
            "extracted_date": "2024-01-15T10:30:00",
            "extracted_measurement": 12345.67,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = write_to_bigquery(state)
        
        assert result["bigquery_success"] is True
    
    @patch('src.twilio_energy_monitor.nodes.bigquery_writer.bigquery.Client')
    def test_write_to_bigquery_missing_data(self, mock_client):
        """Test BigQuery write with missing data."""
        state = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": [],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = write_to_bigquery(state)
        
        assert result["bigquery_success"] is False


class TestResponseGenerator:
    """Tests for the response generator sub-agent."""
    
    def test_format_success_message(self):
        """Test success message formatting."""
        message = format_success_message("2024-01-15", 12345.67)
        
        assert "✅" in message
        assert "12345.67" in message
        assert "2024-01-15" in message
    
    def test_format_error_message(self):
        """Test error message formatting."""
        message = format_error_message()
        
        assert "❌" in message
        assert "Failed" in message
    
    @patch('src.twilio_energy_monitor.nodes.agents.responder.Client')
    def test_generate_response_success(self, mock_twilio_client):
        """Test response generation on success."""
        # Mock Twilio client
        mock_client = Mock()
        mock_message = Mock()
        mock_message.sid = "test_message_sid"
        mock_client.messages.create.return_value = mock_message
        mock_twilio_client.return_value = mock_client
        
        state = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": [],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": None,
            "extracted_date": "2024-01-15T10:30:00",
            "extracted_measurement": 12345.67,
            "bigquery_success": True,
            "response_message": ""
        }
        
        result = generate_response(state)
        
        assert "✅" in result["response_message"]
        assert "12345.67" in result["response_message"]
    
    @patch('src.twilio_energy_monitor.nodes.agents.responder.Client')
    def test_generate_response_failure(self, mock_twilio_client):
        """Test response generation on failure."""
        # Mock Twilio client
        mock_client = Mock()
        mock_message = Mock()
        mock_message.sid = "test_message_sid"
        mock_client.messages.create.return_value = mock_message
        mock_twilio_client.return_value = mock_client
        
        state = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "",
            "media_urls": [],
            "has_image": True,
            "is_energy_counter": True,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        
        result = generate_response(state)
        
        assert "❌" in result["response_message"]
