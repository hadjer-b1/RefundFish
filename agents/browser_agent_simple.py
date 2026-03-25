"""
RefundFish - Simple AI Agent as described
For TinyFish competition - uses goal-based prompting
"""

import requests
import json
import re
from typing import Optional
from config.settings import TINYFISH_API_KEY
from config.logger import setup_logger

logger = setup_logger("browser_agent")

def extract_price(text: str) -> Optional[float]:
    """Extract first number from text"""
    if not isinstance(text, str):
        return None
    
    numbers = re.findall(r'\$?\s?(\d+(?:,\d+)?(?:\.\d+)?)', str(text))
    if not numbers:
        return None
    
    try:
        return float(numbers[0].replace(",", ""))
    except ValueError:
        return None

def get_current_price(hotel_name: str, dates: str) -> Optional[float]:
    """
    SIMPLE VERSION - As user described
    Uses TinyFish with basic goal-based prompting
    """
    
    logger.info(f"TinyFish: {hotel_name} ({dates})")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"}
    
    # Simple goal as user described - returns whatever TinyFish gets
    goal = f"Search for {hotel_name} prices for {dates}. Return only the price number."
    
    payload = {"url": "https://www.google.com", "goal": goal}
    
    try:
        logger.debug("Calling TinyFish agent...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response_text = response.text
        
        logger.debug(f"Response received: {response_text[:200]}")
        
        # Try to extract price from response
        price = extract_price(response_text)
        if price:
            logger.info(f"Found price: ${price}")
            return price
        
        # Show what we got
        logger.warning(f"Response: {response_text[:300]}")
        return None
        
    except Exception as e:
        logger.error(f"TinyFish error: {e}")
        return None

__all__ = ['get_current_price']
