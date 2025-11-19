"""Plot generation tool for creating visual charts of energy consumption data."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from google.cloud import bigquery
from google.api_core import exceptions
from langchain_core.tools import tool
import plotly.graph_objects as go

from ....config import settings

# Configure logging
logger = logging.getLogger(__name__)


def _get_plot_output_dir() -> Path:
    """Get plot output directory from settings with fallback to /tmp."""
    output_dir = getattr(settings, 'plot_output_dir', '/tmp')
    return Path(output_dir)


@tool
def generate_plot(days: int = 30) -> str:
    """Generate a plot showing energy consumption over time.
    
    This tool creates a line chart visualization of energy meter readings over
    a specified time period. The plot shows dates on the x-axis and energy
    measurements (in kWh) on the y-axis. Use this when users want to see trends,
    visualize their consumption patterns, or need a graphical representation of
    their energy usage.
    
    Args:
        days: Number of days to include in the plot (default 30)
    
    Returns:
        Path to the generated plot image file, or error message
        
    Requirements:
        - 10.1: Create chart visualization when agent determines plot is needed
        - 10.2: Generate charts with dates on x-axis and measurements on y-axis
        - 10.3: Save generated chart as image file
        - 10.4: Handle cases with insufficient data (< 2 readings)
    """
    # Validate days parameter
    if days < 1:
        days = 1
    elif days > 365:
        days = 365
    
    client: Optional[bigquery.Client] = None
    
    try:
        # Initialize BigQuery client
        try:
            client = bigquery.Client(project=settings.google_cloud_project)
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            return "Error: Unable to connect to database to generate plot."
        
        # Define table reference
        table_ref = f"{settings.google_cloud_project}.{settings.bigquery_dataset}.{settings.bigquery_table}"
        
        # Calculate date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Build query to retrieve readings within date range
        query = f"""
        SELECT date, measurement
        FROM `{table_ref}`
        WHERE date >= '{start_date}'
        ORDER BY date ASC
        """
        
        logger.info(f"Querying readings from {start_date} to {end_date} for plot generation")
        
        # Execute query
        try:
            query_job = client.query(query)
            results = query_job.result()
        except exceptions.NotFound:
            logger.warning(f"Table {table_ref} not found")
            return "Error: No readings found. The energy readings table doesn't exist yet."
        except exceptions.GoogleAPIError as e:
            logger.error(f"BigQuery query failed: {e}")
            return "Error: Unable to retrieve readings from database."
        
        # Extract data from results
        dates = []
        measurements = []
        
        for row in results:
            dates.append(row.date)
            measurements.append(row.measurement)
        
        # Handle insufficient data (< 2 readings)
        if len(dates) < 2:
            logger.info(f"Insufficient data for plot: {len(dates)} readings found")
            if len(dates) == 0:
                return f"Error: No readings found in the last {days} days. Cannot generate plot."
            else:
                return f"Error: Only 1 reading found in the last {days} days. Need at least 2 readings to generate a plot."
        
        logger.info(f"Generating plot with {len(dates)} readings")
        
        # Create plotly figure
        fig = go.Figure()
        
        # Add line trace with markers
        fig.add_trace(go.Scatter(
            x=dates,
            y=measurements,
            mode='lines+markers',
            name='Energy Reading',
            line=dict(color='#2E86AB', width=2),
            marker=dict(size=8, color='#2E86AB')
        ))
        
        # Customize layout
        fig.update_layout(
            title=dict(
                text=f'Energy Consumption - Last {days} Days',
                font=dict(size=18, family='Arial, sans-serif')
            ),
            xaxis=dict(
                title='Date',
                titlefont=dict(size=14),
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)'
            ),
            yaxis=dict(
                title='Energy Consumption (kWh)',
                titlefont=dict(size=14),
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)'
            ),
            plot_bgcolor='white',
            width=800,
            height=600,
            hovermode='x unified'
        )
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = _get_plot_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        plot_filename = f"energy_plot_{timestamp}.png"
        plot_path = output_dir / plot_filename
        
        # Save plot as PNG
        fig.write_image(str(plot_path), format='png')
        
        logger.info(f"Plot saved to {plot_path}")
        
        return str(plot_path)
        
    except Exception as e:
        logger.error(f"Unexpected error generating plot: {e}", exc_info=True)
        return f"Error: An unexpected error occurred while generating the plot."
    
    finally:
        # Close client connection
        if client:
            try:
                client.close()
            except Exception as e:
                logger.warning(f"Error closing BigQuery client: {e}")
