"""Configuration management for Twilio Energy Monitor."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Twilio Configuration
    twilio_account_sid: str = "test_sid"
    twilio_auth_token: str = "test_token"
    twilio_phone_number: str = "+1234567890"

    # Google Cloud Configuration
    google_cloud_project: str = "test-project"
    vertex_ai_location: str = "us-central1"

    # BigQuery Configuration
    bigquery_dataset: str = "energy_monitoring"
    bigquery_table: str = "meter_readings"

    # Application Configuration
    environment: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
