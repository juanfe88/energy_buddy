"""Electricity price query tool for fetching current electricity prices in France."""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from langchain_core.tools import tool

from ....config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Fallback price in EUR/kWh
FALLBACK_PRICE = 0.20

# Cache file location
CACHE_DIR = Path("/tmp/twilio_energy_monitor")
CACHE_FILE = CACHE_DIR / "electricity_price_cache.json"


def _get_cache_ttl_hours() -> int:
    """Get cache TTL from settings with fallback to 24 hours."""
    return getattr(settings, 'electricity_price_cache_hours', 24)


def _read_cache() -> Optional[Dict[str, Any]]:
    """Read cached price data from file.
    
    Returns:
        Dictionary with 'price', 'timestamp', and 'source' keys, or None if cache invalid
    """
    try:
        if not CACHE_FILE.exists():
            logger.debug("Cache file does not exist")
            return None
        
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
        
        # Validate cache structure
        if not all(key in cache_data for key in ['price', 'timestamp', 'source']):
            logger.warning("Cache file has invalid structure")
            return None
        
        # Check if cache is expired
        cached_time = datetime.fromisoformat(cache_data['timestamp'])
        ttl_hours = _get_cache_ttl_hours()
        expiry_time = cached_time + timedelta(hours=ttl_hours)
        
        if datetime.now() > expiry_time:
            logger.info(f"Cache expired (TTL: {ttl_hours} hours)")
            return None
        
        logger.info(f"Using cached price from {cached_time.strftime('%Y-%m-%d %H:%M:%S')}")
        return cache_data
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to read cache: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading cache: {e}")
        return None


def _write_cache(price: float, source: str) -> None:
    """Write price data to cache file.
    
    Args:
        price: Price in EUR/kWh
        source: Source of the price data (e.g., 'api', 'fallback')
    """
    try:
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        cache_data = {
            'price': price,
            'timestamp': datetime.now().isoformat(),
            'source': source
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        logger.info(f"Cached price {price} EUR/kWh from {source}")
        
    except Exception as e:
        logger.error(f"Failed to write cache: {e}")


def _fetch_price_from_api() -> Optional[float]:
    """Fetch current electricity price from external API.
    
    Returns:
        Price in EUR/kWh, or None if API call fails
    """
    api_url = getattr(settings, 'electricity_price_api_url', '')
    
    if not api_url:
        logger.debug("No API URL configured")
        return None
    
    try:
        import httpx
        
        logger.info(f"Fetching price from API: {api_url}")
        
        # Make API request with timeout
        response = httpx.get(api_url, timeout=5.0)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract price from response (adjust based on actual API structure)
        # This is a generic implementation - may need adjustment for specific API
        price = None
        if isinstance(data, dict):
            # Try common field names
            for field in ['price', 'value', 'rate', 'tariff']:
                if field in data:
                    price = float(data[field])
                    break
        
        if price is None:
            logger.warning("Could not extract price from API response")
            return None
        
        logger.info(f"Fetched price from API: {price} EUR/kWh")
        return price
        
    except ImportError:
        logger.error("httpx library not available for API calls")
        return None
    except httpx.TimeoutException:
        logger.warning("API request timed out")
        return None
    except httpx.HTTPError as e:
        logger.warning(f"API request failed: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to parse API response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching price from API: {e}")
        return None


@tool
def get_electricity_price() -> str:
    """Get the current electricity price per kilowatt-hour in France.
    
    This tool retrieves the current electricity price in France, using cached
    data when available (within 24-hour TTL) or fetching from an external API.
    If the API is unavailable, it returns a fallback price. Use this when users
    ask about electricity costs, want to calculate their energy expenses, or
    need current pricing information.
    
    Returns:
        Current price in EUR/kWh with timestamp and source information
        
    Requirements:
        - 9.1: Retrieve current price per kilowatt-hour for electricity in France
        - 9.2: Fetch pricing data from reliable external API or data source
        - 9.3: Return price in euros per kWh
        - 9.4: Return cached fallback price with timestamp if data unavailable
    """
    try:
        # Try to read from cache first
        cached_data = _read_cache()
        if cached_data:
            price = cached_data['price']
            timestamp = datetime.fromisoformat(cached_data['timestamp'])
            source = cached_data['source']
            
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M')
            return (
                f"Current electricity price in France: €{price:.4f}/kWh\n"
                f"Source: {source}\n"
                f"Last updated: {timestamp_str}"
            )
        
        # Try to fetch from API
        api_price = _fetch_price_from_api()
        if api_price is not None:
            _write_cache(api_price, 'api')
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            return (
                f"Current electricity price in France: €{api_price:.4f}/kWh\n"
                f"Source: api\n"
                f"Last updated: {timestamp_str}"
            )
        
        # Fall back to static price
        logger.info("Using fallback price")
        _write_cache(FALLBACK_PRICE, 'fallback')
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        return (
            f"Current electricity price in France: €{FALLBACK_PRICE:.4f}/kWh\n"
            f"Source: fallback (average price)\n"
            f"Last updated: {timestamp_str}\n"
            f"Note: This is an estimated average price as real-time data is unavailable."
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in get_electricity_price: {e}", exc_info=True)
        # Return fallback price even on unexpected errors
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        return (
            f"Current electricity price in France: €{FALLBACK_PRICE:.4f}/kWh\n"
            f"Source: fallback (average price)\n"
            f"Last updated: {timestamp_str}\n"
            f"Note: This is an estimated average price."
        )
