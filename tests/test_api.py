"""API tests for FastAPI endpoints."""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""
    
    def test_health_check(self):
        """Test health endpoint returns 200 and correct status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "twilio-energy-monitor"


class TestTwilioWebhook:
    """Tests for the Twilio webhook endpoint."""
    
    @patch('main.invoke_workflow')
    @patch('main.verify_twilio_signature')
    def test_webhook_with_valid_signature(self, mock_verify, mock_workflow):
        """Test webhook accepts request with valid Twilio signature."""
        # Mock signature verification
        mock_verify.return_value = True
        
        # Mock workflow execution
        mock_final_state = {
            "message_sid": "test_sid",
            "from_number": "+1234567890",
            "message_body": "Test",
            "media_urls": [],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        mock_workflow.return_value = mock_final_state
        
        # Simulate Twilio webhook payload
        form_data = {
            "MessageSid": "test_sid",
            "From": "whatsapp:+1234567890",
            "Body": "Test message",
            "NumMedia": "0"
        }
        
        headers = {
            "X-Twilio-Signature": "valid_signature"
        }
        
        response = client.post("/webhook/twilio", data=form_data, headers=headers)
        
        assert response.status_code == 200
        mock_verify.assert_called_once()
        mock_workflow.assert_called_once()
    
    @patch('main.verify_twilio_signature')
    def test_webhook_with_invalid_signature(self, mock_verify):
        """Test webhook rejects request with invalid Twilio signature."""
        # Mock signature verification failure
        mock_verify.return_value = False
        
        form_data = {
            "MessageSid": "test_sid",
            "From": "whatsapp:+1234567890",
            "Body": "Test message",
            "NumMedia": "0"
        }
        
        headers = {
            "X-Twilio-Signature": "invalid_signature"
        }
        
        response = client.post("/webhook/twilio", data=form_data, headers=headers)
        
        assert response.status_code == 403
    
    @patch('main.invoke_workflow')
    @patch('main.verify_twilio_signature')
    def test_webhook_extracts_message_data(self, mock_verify, mock_workflow):
        """Test webhook correctly extracts message content and media URLs."""
        # Mock signature verification
        mock_verify.return_value = True
        
        # Mock workflow execution
        mock_final_state = {
            "message_sid": "test_sid",
            "from_number": "whatsapp:+1234567890",
            "message_body": "Here's my meter",
            "media_urls": ["https://api.twilio.com/media/image.jpg"],
            "has_image": False,
            "is_energy_counter": False,
            "image_path": None,
            "extracted_date": None,
            "extracted_measurement": None,
            "bigquery_success": False,
            "response_message": ""
        }
        mock_workflow.return_value = mock_final_state
        
        # Simulate Twilio webhook with media
        form_data = {
            "MessageSid": "test_sid",
            "From": "whatsapp:+1234567890",
            "Body": "Here's my meter",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/image.jpg"
        }
        
        headers = {
            "X-Twilio-Signature": "valid_signature"
        }
        
        response = client.post("/webhook/twilio", data=form_data, headers=headers)
        
        assert response.status_code == 200
        
        # Verify workflow was called with correct initial state
        call_args = mock_workflow.call_args[0][0]
        assert call_args["message_sid"] == "test_sid"
        assert call_args["from_number"] == "whatsapp:+1234567890"
        assert call_args["message_body"] == "Here's my meter"
        assert len(call_args["media_urls"]) == 1
    
    @patch('main.invoke_workflow')
    @patch('main.verify_twilio_signature')
    def test_webhook_returns_200_on_workflow_error(self, mock_verify, mock_workflow):
        """Test webhook returns 200 even if workflow fails (to prevent Twilio retries)."""
        # Mock signature verification
        mock_verify.return_value = True
        
        # Mock workflow raising an exception
        mock_workflow.side_effect = Exception("Workflow error")
        
        form_data = {
            "MessageSid": "test_sid",
            "From": "whatsapp:+1234567890",
            "Body": "Test message",
            "NumMedia": "0"
        }
        
        headers = {
            "X-Twilio-Signature": "valid_signature"
        }
        
        response = client.post("/webhook/twilio", data=form_data, headers=headers)
        
        # Should still return 200 to prevent Twilio retries
        assert response.status_code == 200
