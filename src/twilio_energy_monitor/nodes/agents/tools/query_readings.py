"""Reading query tool for retrieving historical energy readings from BigQuery."""

import logging
from typing import Optional
from google.cloud import bigquery
from google.api_core import exceptions
from langchain_core.tools import tool

from ....config import settings

# Configure logging
logger = logging.getLogger(__name__)


@tool
def query_readings(num_readings: int = 10) -> str:
    """Retrieve the latest N energy meter readings from the database.
    
    This tool queries the BigQuery table to fetch historical energy readings,
    ordered by date in descending order (most recent first). Use this when
    users ask about their recent consumption, want to see their reading history,
    or need data for analysis.
    
    Args:
        num_readings: Number of readings to retrieve (default 10, max 100)
    
    Returns:
        Formatted string with dates and measurements, or error message
        
    Requirements:
        - 8.1: Retrieve latest N energy readings from BigQuery
        - 8.2: Accept parameter for number of readings (max 100)
        - 8.3: Return readings in chronological order with date and measurement
        - 8.4: Handle cases where fewer readings exist than requested
    """
    # Validate and cap num_readings
    if num_readings < 1:
        num_readings = 1
    elif num_readings > 100:
        num_readings = 100
    
    client: Optional[bigquery.Client] = None
    
    try:
        # Initialize BigQuery client
        try:
            client = bigquery.Client(project=settings.google_cloud_project)
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            return f"Error: Unable to connect to database. Please try again later."
        
        # Define table reference
        table_ref = f"{settings.google_cloud_project}.{settings.bigquery_dataset}.{settings.bigquery_table}"
        
        # Build query to retrieve latest N readings
        query = f"""
        SELECT date, measurement
        FROM `{table_ref}`
        ORDER BY date DESC
        LIMIT {num_readings}
        """
        
        logger.info(f"Querying {num_readings} readings from {table_ref}")
        
        # Execute query
        try:
            query_job = client.query(query)
            results = query_job.result()
        except exceptions.NotFound:
            logger.warning(f"Table {table_ref} not found")
            return "No readings found. The energy readings table doesn't exist yet. Please submit your first reading."
        except exceptions.GoogleAPIError as e:
            logger.error(f"BigQuery query failed: {e}")
            return f"Error: Unable to retrieve readings from database."
        
        # Format results
        readings = []
        for row in results:
            date_str = row.date.strftime('%Y-%m-%d')
            measurement = row.measurement
            readings.append(f"{date_str}: {measurement:.2f} kWh")
        
        # Handle empty results
        if not readings:
            logger.info("No readings found in table")
            return "No readings found. You haven't submitted any energy readings yet."
        
        # Handle case where fewer readings exist than requested
        actual_count = len(readings)
        if actual_count < num_readings:
            logger.info(f"Found {actual_count} readings (requested {num_readings})")
        
        # Format response
        header = f"Latest {actual_count} energy reading{'s' if actual_count != 1 else ''}:\n"
        return header + "\n".join(readings)
        
    except Exception as e:
        logger.error(f"Unexpected error querying readings: {e}", exc_info=True)
        return "Error: An unexpected error occurred while retrieving readings."
    
    finally:
        # Close client connection
        if client:
            try:
                client.close()
            except Exception as e:
                logger.warning(f"Error closing BigQuery client: {e}")
