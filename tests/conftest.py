"""Pytest configuration and fixtures."""

import os
import pytest
from unittest.mock import patch


@pytest.fixture(scope="session", autouse=True)
def mock_env_variables():
    """Mock environment variables for testing."""
    env_vars = {
        "TWILIO_ACCOUNT_SID": "test_account_sid",
        "TWILIO_AUTH_TOKEN": "test_auth_token",
        "TWILIO_PHONE_NUMBER": "+1234567890",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "VERTEX_AI_LOCATION": "us-central1",
        "BIGQUERY_DATASET": "test_dataset",
        "BIGQUERY_TABLE": "test_table",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "ERROR"
    }
    
    with patch.dict(os.environ, env_vars):
        yield
