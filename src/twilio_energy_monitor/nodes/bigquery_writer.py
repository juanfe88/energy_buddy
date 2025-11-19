"""BigQuery writer functions for persisting energy counter readings."""

import logging
from datetime import datetime
from google.cloud import bigquery
from google.api_core import exceptions

from ..config import settings
from ..utils.retry import exponential_backoff_retry

# Configure logging
logger = logging.getLogger(__name__)


def check_table_exists(client: bigquery.Client, dataset_id: str, table_id: str) -> bool:
    """Check if BigQuery table exists.
    
    Args:
        client: BigQuery client instance
        dataset_id: Dataset ID
        table_id: Table ID
        
    Returns:
        True if table exists, False otherwise
        
    Requirements:
        - 3.1: Check if BigQuery table exists
    """
    table_ref = f"{settings.google_cloud_project}.{dataset_id}.{table_id}"
    try:
        client.get_table(table_ref)
        logger.info(f"Table {table_ref} exists")
        return True
    except exceptions.NotFound:
        logger.info(f"Table {table_ref} not found")
        return False


def create_table(client: bigquery.Client, dataset_id: str, table_id: str) -> None:
    """Create BigQuery table with proper schema.
    
    Args:
        client: BigQuery client instance
        dataset_id: Dataset ID
        table_id: Table ID
        
    Raises:
        exceptions.GoogleAPIError: If table creation fails
        
    Requirements:
        - 3.2: Create table with schema (date, measurement, recorded_at, source_phone)
    """
    # Ensure dataset exists
    dataset_ref = f"{settings.google_cloud_project}.{dataset_id}"
    try:
        client.get_dataset(dataset_ref)
        logger.info(f"Dataset {dataset_ref} exists")
    except exceptions.NotFound:
        logger.info(f"Creating dataset {dataset_ref}")
        try:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            client.create_dataset(dataset, timeout=30)
            logger.info(f"Created dataset {dataset_ref}")
        except exceptions.GoogleAPIError as e:
            logger.error(f"Failed to create dataset {dataset_ref}: {e}")
            raise
    except exceptions.GoogleAPIError as e:
        logger.error(f"Error checking dataset {dataset_ref}: {e}")
        raise
    
    # Define table schema
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("measurement", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("source_phone", "STRING", mode="NULLABLE"),
    ]
    
    # Create table
    table_ref = f"{settings.google_cloud_project}.{dataset_id}.{table_id}"
    try:
        table = bigquery.Table(table_ref, schema=schema)
        table = client.create_table(table)
        logger.info(f"Created table {table_ref}")
    except exceptions.GoogleAPIError as e:
        logger.error(f"Failed to create table {table_ref}: {e}")
        raise


def merge_record(
    client: bigquery.Client,
    table_ref: str,
    date: str,
    measurement: float,
    source_phone: str
) -> None:
    """Insert or update record using MERGE statement.
    
    This function uses a MERGE statement to handle duplicate dates by
    updating existing records instead of creating duplicates.
    
    Args:
        client: BigQuery client instance
        table_ref: Full table reference (project.dataset.table)
        date: Date string in ISO format
        measurement: Measurement value
        source_phone: Source phone number
        
    Raises:
        exceptions.GoogleAPIError: If MERGE operation fails
        
    Requirements:
        - 3.3: Insert record with extracted date and measurement
        - 3.4: Handle duplicate entries by updating existing records
    """
    # Parse date to ensure it's in correct format
    try:
        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
        date_str = date_obj.strftime('%Y-%m-%d')
    except ValueError as e:
        logger.warning(f"Error parsing date {date}: {e}")
        # Fallback: try to extract date part
        try:
            date_str = date.split('T')[0]
            # Validate format
            datetime.strptime(date_str, '%Y-%m-%d')
        except (ValueError, IndexError) as e2:
            logger.error(f"Cannot parse date {date}: {e2}")
            raise ValueError(f"Invalid date format: {date}")
    
    # Escape single quotes in source_phone for SQL safety
    safe_source_phone = source_phone.replace("'", "''") if source_phone else ""
    
    # MERGE query to insert or update
    merge_query = f"""
    MERGE `{table_ref}` T
    USING (
        SELECT
            DATE('{date_str}') as date,
            {measurement} as measurement,
            CURRENT_TIMESTAMP() as recorded_at,
            '{safe_source_phone}' as source_phone
    ) S
    ON T.date = S.date
    WHEN MATCHED THEN
        UPDATE SET
            measurement = S.measurement,
            recorded_at = S.recorded_at,
            source_phone = S.source_phone
    WHEN NOT MATCHED THEN
        INSERT (date, measurement, recorded_at, source_phone)
        VALUES (S.date, S.measurement, S.recorded_at, S.source_phone)
    """
    
    logger.info(f"Executing MERGE query for date={date_str}")
    
    try:
        # Execute query
        query_job = client.query(merge_query)
        query_job.result()  # Wait for completion
        logger.info(f"MERGE completed successfully")
    except exceptions.GoogleAPIError as e:
        logger.error(f"BigQuery MERGE operation failed: {e}")
        raise


@exponential_backoff_retry(
    max_retries=1,
    initial_delay=2.0,
    exceptions=(exceptions.GoogleAPIError, exceptions.RetryError)
)
def merge_record_with_retry(
    client: bigquery.Client,
    table_ref: str,
    date: str,
    measurement: float,
    source_phone: str
) -> None:
    """Wrapper for merge_record with retry logic for transient errors.
    
    Args:
        client: BigQuery client instance
        table_ref: Full table reference (project.dataset.table)
        date: Date string in ISO format
        measurement: Measurement value
        source_phone: Source phone number
        
    Raises:
        exceptions.GoogleAPIError: If MERGE operation fails after retries
    """
    merge_record(client, table_ref, date, measurement, source_phone)


def write_to_bigquery(state: dict) -> dict:
    """Node function to persist energy reading to BigQuery.
    
    This node checks if the BigQuery table exists, creates it if missing,
    and inserts or updates the energy reading record using a MERGE statement
    to handle duplicate dates. Updates the bigquery_success flag in state.
    Implements comprehensive error handling and retry logic for robustness.
    
    Args:
        state: Current agent state containing extracted_date, extracted_measurement, and from_number
        
    Returns:
        Dictionary with updated state field:
        - bigquery_success: Boolean indicating if the write operation succeeded
        
    Requirements:
        - 3.1: Check if BigQuery table exists
        - 3.2: Create table if it doesn't exist with proper schema
        - 3.3: Insert record with extracted date and measurement
        - 3.4: Handle duplicate entries by updating existing records
    """
    bigquery_success = False
    
    # Validate required data
    extracted_date = state.get("extracted_date")
    extracted_measurement = state.get("extracted_measurement")
    from_number = state.get("from_number")
    
    if not extracted_date or extracted_measurement is None:
        logger.warning("Missing extracted_date or extracted_measurement, skipping BigQuery write")
        return {"bigquery_success": bigquery_success}
    
    # Validate measurement value
    if not isinstance(extracted_measurement, (int, float)) or extracted_measurement < 0:
        logger.error(f"Invalid measurement value: {extracted_measurement}")
        return {"bigquery_success": bigquery_success}
    
    client = None
    try:
        # Initialize BigQuery client (uses Application Default Credentials)
        try:
            client = bigquery.Client(project=settings.google_cloud_project)
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            raise
        
        # Define table reference
        dataset_id = settings.bigquery_dataset
        table_id = settings.bigquery_table
        table_ref = f"{settings.google_cloud_project}.{dataset_id}.{table_id}"
        
        logger.info(f"Checking if table exists: {table_ref}")
        
        # Check if table exists, create if not
        try:
            if not check_table_exists(client, dataset_id, table_id):
                logger.info(f"Table {table_ref} not found, creating...")
                create_table(client, dataset_id, table_id)
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error checking/creating table: {e}")
            raise
        
        # Insert or update record using MERGE statement with retry
        try:
            merge_record_with_retry(
                client=client,
                table_ref=table_ref,
                date=extracted_date,
                measurement=extracted_measurement,
                source_phone=from_number
            )
        except exceptions.GoogleAPIError as e:
            logger.error(f"Error merging record after retries: {e}")
            raise
        
        bigquery_success = True
        logger.info(f"Successfully wrote record to BigQuery: date={extracted_date}, measurement={extracted_measurement}")
        
    except exceptions.PermissionDenied as e:
        logger.error(f"Permission denied accessing BigQuery: {e}")
        logger.error("Check that Application Default Credentials have BigQuery permissions")
    except exceptions.NotFound as e:
        logger.error(f"BigQuery resource not found: {e}")
    except exceptions.GoogleAPIError as e:
        logger.error(f"Google API error writing to BigQuery: {e}")
    except Exception as e:
        logger.error(f"Unexpected error writing to BigQuery: {e}", exc_info=True)
    finally:
        # Close client connection if it was created
        if client:
            try:
                client.close()
            except Exception as e:
                logger.warning(f"Error closing BigQuery client: {e}")
    
    return {"bigquery_success": bigquery_success}
