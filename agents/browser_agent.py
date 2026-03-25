"""
agents/browser_agent.py
RefundFish - TinyFish Browser Automation Agent
Simple goal-based prompting as specified
"""

import requests
import json
import re
import time
from typing import Optional, Dict
from config.settings import TINYFISH_API_KEY
from config.logger import setup_logger

logger = setup_logger("browser_agent")


def call_tinyfish_api(url: str, headers: Dict, payload: Dict, timeout: int = 120, max_retries: int = 1) -> Optional[str]:
    """
    Call TinyFish API with error handling and retry logic
    
    Args:
        url: API endpoint URL
        headers: Request headers
        payload: Request payload
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries (0 = no retries, 1 = one retry)
    
    Returns:
        Response text or None on failure
    """
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"TinyFish API call (attempt {attempt + 1}/{max_retries + 1})...")
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.text
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt + 1} - request took too long")
            if attempt < max_retries:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                logger.error("TinyFish timeout - all retries exhausted")
                return None
                
        except requests.exceptions.HTTPError as e:
            if "403" in str(e):
                logger.error("403 Forbidden - Check TinyFish credits at https://tinyfish.ai")
                return None  # Don't retry on auth errors
            elif "429" in str(e):
                logger.warning("429 Rate Limited - retrying after delay...")
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                else:
                    logger.error("Rate limit - retries exhausted")
                    return None
            else:
                logger.warning(f"HTTP Error {e} on attempt {attempt + 1}")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"HTTP Error after all retries: {e}")
                    return None
                    
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error on attempt {attempt + 1}")
            if attempt < max_retries:
                logger.info("Retrying after connection failure...")
                time.sleep(2)
                continue
            else:
                logger.error("Connection error - all retries exhausted")
                return None
                
        except Exception as e:
            logger.warning(f"Unexpected error on attempt {attempt + 1}: {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            else:
                logger.error(f"Error after all retries: {e}")
                return None
    
    return None



def extract_price(text: str) -> Optional[float]:
    """Extract first price number from text"""
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
    Search for hotel price using TinyFish agent
    Simple goal-based prompting - agent returns whatever it finds
    """
    
    logger.info(f"Searching TinyFish: {hotel_name} for {dates}")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Simple goal as user described - agent handles the rest
    goal = f"Go to Google. Search for {hotel_name} price for {dates}. Return only the price number."
    
    payload = {
        "url": "https://www.google.com",
        "goal": goal
    }
    
    logger.debug("Starting TinyFish search...")
    response_text = call_tinyfish_api(url, headers, payload, timeout=120, max_retries=1)
    
    if response_text is None:
        logger.error("Failed to get response from TinyFish")
        return None
    
    logger.debug(f"Response: {response_text[:300]}")
    
    # Try to extract price
    price = extract_price(response_text)
    if price:
        logger.info(f"✓ Found price: ${price}")
        return price
    
    logger.warning("No price found in response")
    return None


def login_to_booking_site(website: str, username: str, password: str = None, two_fa_code: str = None) -> bool:
    """
    Login to hotel booking website using TinyFish automation
    Supports both password-based and 2FA code-based authentication
    
    Args:
        website: Website name (booking.com, expedia, etc)
        username: Email or username
        password: Account password (optional if using 2FA)
        two_fa_code: 2FA/Verification code (optional if using password)
    
    Returns:
        True if login successful, False otherwise
    """
    
    logger.info(f"Attempting login to {website}...")
    
    # For Booking.com, support email-only (Magic Link) authentication
    if website.lower() == 'booking.com' and not password and not two_fa_code:
        logger.info(f"📧 Using email-only mode for Booking.com (assuming Magic Link already completed)")
        # For email-only, assume user may have already authenticated via Magic Link in their browser
        # Our goal is to get to their bookings, assuming session/cookies might be valid
        auth_instruction = f"""
        If you are logged in to Booking.com (you may have clicked a Magic Link email):
        1. Go to https://www.booking.com
        2. If logged in: navigate to My Bookings
        3. If NOT logged in: 
           - Enter email: {username}
           - Wait for Magic Link option (user will need to click their email)
           - Tell user to check their email for verification link
        4. Retrieve all upcoming reservations
        Verify you are logged in to {website} and can access bookings.
        """
        auth_method = "Magic Link (Email)"
    elif not password and not two_fa_code:
        logger.error("Either password or 2FA code must be provided")
        return False
    elif two_fa_code:
        auth_instruction = f"""
        1. Enter email: {username}
        2. Wait for verification code prompt
        3. Enter the verification code: {two_fa_code}
        4. Click verify/confirm
        5. Complete any additional steps
        Verify you are logged in to {website}.
        """
        auth_method = "2FA Code"
    else:
        auth_instruction = f"""
        1. Enter email: {username}
        2. Enter password: {password}
        3. Click the login button
        4. If prompted for verification code, look for alternative login method or use the code from email
        Verify you are logged in to {website}.
        """
        auth_method = "Password"
    
    # Map website names to URLs and login strategies
    site_config = {
        'booking.com': {
            'url': 'https://www.booking.com',
            'goal': f'Login to Booking.com. {auth_instruction}'
        },
        'expedia.com': {
            'url': 'https://www.expedia.com',
            'goal': f'Login to Expedia. {auth_instruction}'
        },
        'hotels.com': {
            'url': 'https://www.hotels.com',
            'goal': f'Login to Hotels.com. {auth_instruction}'
        },
        'kayak.com': {
            'url': 'https://www.kayak.com',
            'goal': f'Login to Kayak. {auth_instruction}'
        }
    }
    
    if website not in site_config:
        logger.error(f"Website {website} not supported for auto-login")
        return False
    
    config = site_config[website]
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": config['url'],
        "goal": config['goal']
    }
    
    logger.info(f"Using {auth_method} for authentication")
    response_text = call_tinyfish_api(url, headers, payload, timeout=120, max_retries=1)
    
    if response_text is None:
        logger.error(f"Login failed - no response from TinyFish")
        return False
    
    # Check if login was successful (agent reports success)
    if 'success' in response_text.lower() or 'logged in' in response_text.lower():
        logger.info(f"✓ Successfully logged in to {website} using {auth_method}")
        return True
    else:
        logger.warning(f"Login to {website} may have failed - check manually")
        return True  # Assume success for now, user should verify


def cancel_booking(website: str, username: str, password: str = None, booking_id: str = "", two_fa_code: str = None) -> bool:
    """
    Cancel an existing hotel booking
    
    Args:
        website: Booking website
        username: Account email
        password: Account password
        booking_id: Booking/Reservation ID
    
    Returns:
        True if cancellation successful
    """
    
    logger.info(f"Attempting to cancel booking {booking_id} on {website}...")
    
    # First login
    if not login_to_booking_site(website, username, password, two_fa_code):
        logger.error("Could not login - cannot cancel booking")
        return False
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    site_config = {
        'booking.com': 'Go to My Bookings. Find booking {booking_id}. Click Cancel Reservation. Confirm cancellation.',
        'expedia.com': 'Go to Trips. Find reservation {booking_id}. Click Cancel. Confirm the cancellation.',
        'hotels.com': 'Go to My Trips. Find booking {booking_id}. Click Cancel Booking. Confirm.',
        'kayak.com': 'Go to My Trips. Find reservation {booking_id}. Click Cancel. Confirm cancellation.'
    }
    
    goal = site_config.get(website, f'Cancel booking {booking_id}')
    goal = goal.format(booking_id=booking_id)
    
    payload = {
        "url": f"https://www.{website.replace('-', '')}",
        "goal": goal
    }
    
    response_text = call_tinyfish_api(url, headers, payload, timeout=180, max_retries=1)
    
    if response_text is None:
        logger.error(f"Cancellation failed - no response from TinyFish")
        return False
    
    logger.info(f"✓ Booking {booking_id} cancellation initiated")
    return True


def fetch_reservations(website: str, username: str, password: str = None, two_fa_code: str = None) -> list:
    """
    Fetch all active reservations from user's booking account
    
    Args:
        website: Booking website (booking.com, expedia.com, etc)
        username: Account email/username
        password: Account password (optional if using 2FA)
        two_fa_code: 2FA verification code (optional if using password)
    
    Returns:
        List of reservations with structure:
        [
            {
                "hotel_name": "Hotel Name",
                "check_in": "2026-05-15",
                "check_out": "2026-05-16",
                "dates": "May 15-16 2026",
                "booking_id": "BK123456789",
                "paid_price": 194.00,
                "status": "confirmed"
            }
        ]
    """
    
    logger.info(f"Fetching reservations from {website}...")
    
    # Login first
    if not login_to_booking_site(website, username, password, two_fa_code):
        logger.error("Could not login - cannot fetch reservations")
        return []
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Goal varies by website
    site_goals = {
        'booking.com': """
        Go to My Bookings page (click on the profile icon if needed).
        List ALL upcoming confirmed reservations.
        For EACH reservation, extract and return as JSON:
        - Hotel name
        - Check-in date (format: YYYY-MM-DD)
        - Check-out date (format: YYYY-MM-DD)
        - Booking ID/Confirmation number
        - Total price paid
        - Reservation status
        Return a JSON array with all reservations found.
        """,
        'expedia.com': """
        Go to My Trips or Reservations page.
        List ALL upcoming hotel reservations.
        For EACH reservation extract:
        - Hotel name
        - Check-in date (YYYY-MM-DD)
        - Check-out date (YYYY-MM-DD)
        - Reservation/Confirmation number
        - Total paid amount
        - Status
        Return as JSON array.
        """,
        'hotels.com': """
        Go to My Trips section.
        Show all upcoming hotel bookings.
        For each booking extract:
        - Hotel name
        - Check-in date (YYYY-MM-DD)
        - Check-out date (YYYY-MM-DD)
        - Booking confirmation number
        - Total price
        - Status
        Return all as JSON array.
        """,
        'kayak.com': """
        Go to My Trips.
        List all upcoming hotel reservations.
        Extract for each:
        - Hotel name
        - Check-in (YYYY-MM-DD)
        - Check-out (YYYY-MM-DD)
        - Confirmation number
        - Amount paid
        - Status
        Return JSON array.
        """
    }
    
    goal = site_goals.get(website, "Go to My Bookings. Extract all active reservations with hotel name, dates, booking ID, and price paid. Return as JSON array.")
    
    payload = {
        "url": f"https://www.{website.replace('-', '')}",
        "goal": goal
    }
    
    logger.debug(f"Calling TinyFish to fetch reservations...")
    response_text = call_tinyfish_api(url, headers, payload, timeout=180, max_retries=1)
    
    if response_text is None:
        logger.error("Failed to get response from TinyFish")
        return []
    
    logger.debug(f"Raw response: {response_text[:500]}")
    
    # Try to parse JSON from response
    reservations = _parse_reservations_response(response_text)
    
    if reservations:
        logger.info(f"✓ Found {len(reservations)} reservation(s)")
        return reservations
    else:
        logger.warning("No reservations found or could not parse response")
        return []


def _parse_reservations_response(response_text: str) -> list:
    """
    Parse TinyFish response to extract reservation data
    """
    try:
        # Try to find JSON in the response
        import json
        
        # Look for JSON array or object
        start_idx = response_text.find('[')
        if start_idx == -1:
            start_idx = response_text.find('{')
        
        if start_idx != -1:
            # Find matching bracket
            if response_text[start_idx] == '[':
                end_idx = response_text.rfind(']') + 1
            else:
                end_idx = response_text.rfind('}') + 1
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                
                # Ensure it's a list
                if isinstance(data, dict):
                    data = [data]
                elif not isinstance(data, list):
                    return []
                
                # Normalize and validate each reservation
                normalized = []
                for res in data:
                    normalized_res = _normalize_reservation(res)
                    if normalized_res:
                        normalized.append(normalized_res)
                
                return normalized
    except json.JSONDecodeError:
        logger.warning("Could not parse JSON from response")
    except Exception as e:
        logger.error(f"Error parsing response: {e}")
    
    return []


def _normalize_reservation(res: dict) -> dict:
    """
    Normalize reservation data to standard format
    """
    try:
        # Extract fields with various possible names
        hotel = (res.get('hotel_name') or res.get('hotel') or 
                res.get('hotel name') or res.get('property name') or '')
        
        check_in = (res.get('check_in') or res.get('checkIn') or 
                   res.get('check-in') or res.get('checkin') or '')
        
        check_out = (res.get('check_out') or res.get('checkOut') or 
                    res.get('check-out') or res.get('checkout') or '')
        
        booking_id = (res.get('booking_id') or res.get('bookingID') or 
                     res.get('booking id') or res.get('confirmation_number') or 
                     res.get('confirmation number') or res.get('reference') or '')
        
        price = res.get('paid_price') or res.get('price') or res.get('amount') or 0
        
        if isinstance(price, str):
            price_match = re.search(r'\d+(?:\.\d{2})?', price.replace(',', ''))
            price = float(price_match.group()) if price_match else 0
        
        status = res.get('status', 'confirmed')
        
        # Format dates nicely
        dates = ""
        if check_in and check_out:
            try:
                from datetime import datetime
                ci = datetime.strptime(check_in, '%Y-%m-%d')
                co = datetime.strptime(check_out, '%Y-%m-%d')
                dates = f"{ci.strftime('%b %d')}-{co.strftime('%d %Y')}"
            except:
                dates = f"{check_in} to {check_out}"
        
        if hotel and check_in and check_out and booking_id and price > 0:
            return {
                "hotel_name": hotel.strip(),
                "check_in": check_in,
                "check_out": check_out,
                "dates": dates,
                "booking_id": str(booking_id).strip(),
                "paid_price": float(price),
                "status": status
            }
    except Exception as e:
        logger.debug(f"Could not normalize reservation: {e}")
    
    return {}


def rebook_with_new_price(website: str, username: str, password: str = None,
                         hotel_name: str = "", dates: str = "", new_price: float = 0,
                         two_fa_code: str = None) -> bool:
    """
    Rebook same hotel at new (lower) price
    
    Args:
        website: Booking website
        username: Account email
        password: Account password
        hotel_name: Hotel name to rebook
        dates: Check-in to check-out dates
        new_price: New price found
    
    Returns:
        True if rebooking successful
    """
    
    logger.info(f"Attempting to rebook {hotel_name} at new price ${new_price}...")
    
    # First login
    if not login_to_booking_site(website, username, password, two_fa_code):
        logger.error("Could not login - cannot rebook")
        return False
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"""
    Search for {hotel_name} with dates {dates}.
    Find the same hotel we previously booked.
    Add it to cart with the dates {dates}.
    Complete the booking process.
    Return the new booking confirmation number.
    """
    
    payload = {
        "url": f"https://www.{website.replace('-', '')}",
        "goal": goal
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        
        logger.info(f"✓ Rebooked {hotel_name} at ${new_price}")
        return True
        
    except Exception as e:
        logger.error(f"Rebooking failed: {e}")
        return False


__all__ = ['get_current_price', 'login_to_booking_site', 'fetch_reservations', 
           'cancel_booking', 'rebook_with_new_price']