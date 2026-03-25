"""
utils/helpers.py
================
Minimal helper functions for RefundFish project
Price extraction, date parsing, JSON handling
"""

import re
import json
from typing import Optional, Dict, Any, List
from config.logger import setup_logger

logger = setup_logger("helpers")


def extract_price_from_text(text: str) -> Optional[float]:
    """
    Extract first price from text
    Matches patterns: $123.45 or 123.45 or $1,200
    """
    if not isinstance(text, str):
        return None
    
    # Pattern: optional $, digits with optional commas, optional decimal
    pattern = r'\$?\s?(\d+(?:,\d+)?(?:\.\d{2})?)'
    matches = re.findall(pattern, text)
    
    if not matches:
        return None
    
    try:
        price_str = matches[0].replace(",", "")
        return float(price_str)
    except (ValueError, IndexError):
        return None


def safe_json_parse(text: str) -> Optional[Dict]:
    """Safely parse JSON text"""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {str(e)}")
        return None


def validate_booking_data(booking: Dict) -> bool:
    """Verify booking has all required fields"""
    required_fields = ["hotel_name", "dates", "paid_price"]
    
    for field in required_fields:
        if field not in booking:
            logger.error(f"Missing field in booking: {field}")
            return False
    
    # Verify price is numeric and positive
    try:
        price = float(booking["paid_price"])
        if price <= 0:
            logger.error(f"Price must be positive: {price}")
            return False
    except (ValueError, TypeError):
        logger.error(f"Price must be numeric: {booking['paid_price']}")
        return False
    
    return True

