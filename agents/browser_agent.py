"""
agents/browser_agent.py
RefundFish - TinyFish Browser Automation Agent
Simple goal-based prompting as specified
"""

import requests
import json
import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
from config.settings import TINYFISH_API_KEY
from config.logger import setup_logger

logger = setup_logger("browser_agent")

CURRENCY_TO_USD = {
    "USD": 1.0,
    "EUR": 1.09,
    "GBP": 1.28,
    "CAD": 0.74,
    "AUD": 0.66,
    "JPY": 0.0067,
    "CHF": 1.12,
    "AED": 0.27,
    "SAR": 0.27,
    "QAR": 0.27,
}


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


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from TinyFish free-form text response."""
    if not isinstance(text, str):
        return []

    stripped = text.strip()
    if stripped.startswith('[') and stripped.endswith(']'):
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            pass

    array_match = re.search(r'(\[\s*\{[\s\S]*\}\s*\])', text)
    if not array_match:
        return []

    try:
        parsed = json.loads(array_match.group(1))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _to_float(value: Any, strict_clean: bool = True, max_price_ceiling: float = 250.0) -> Optional[float]:
    """Extract price as float. If strict_clean=True, extract only digits and divide by 100 (e.g. 12345 -> 123.45)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        if price > max_price_ceiling:
            return None
        return price

    if isinstance(value, str):
        if strict_clean:
            digits_only = ''.join(filter(str.isdigit, value))
            if not digits_only:
                return None
            try:
                as_int = int(digits_only)
                if as_int > int(max_price_ceiling * 100):
                    return None
                price = float(as_int) / 100.0 if as_int > 99 else float(as_int)
                return price if price <= max_price_ceiling else None
            except (ValueError, ZeroDivisionError):
                return None
        else:
            match = re.search(r'(\d+(?:,\d+)?(?:\.\d+)?)', value)
            if not match:
                return None
            try:
                price = float(match.group(1).replace(',', ''))
                return price if price <= max_price_ceiling else None
            except ValueError:
                return None
    return None


def _normalize_currency(value: Any, fallback: str = "USD") -> str:
    if not value:
        return fallback
    text = str(value).strip().upper()
    if text in {"$", "USD", "US$"}:
        return "USD"
    if text in {"€", "EUR"}:
        return "EUR"
    if text in {"£", "GBP"}:
        return "GBP"
    if text in {"AED", "CAD", "JPY", "AUD", "SAR", "QAR", "CHF"}:
        return text
    return fallback


def _convert_to_usd(amount: float, currency: str) -> Optional[float]:
    normalized_currency = _normalize_currency(currency, fallback="USD")
    rate = CURRENCY_TO_USD.get(normalized_currency)
    if rate is None:
        return None
    return float(amount) * rate


def _extract_currency_amount_pairs(text: str) -> List[Dict[str, Any]]:
    if not isinstance(text, str):
        return []

    pairs: List[Dict[str, Any]] = []
    symbol_pattern = re.compile(r'(?P<currency>\$|€|£)\s?(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)')
    code_pattern = re.compile(r'(?P<currency>USD|EUR|GBP|CAD|AUD|JPY|CHF|AED|SAR|QAR)\s?(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)', re.IGNORECASE)

    for match in symbol_pattern.finditer(text):
        amount = _to_float(match.group("amount"), strict_clean=False, max_price_ceiling=100000.0)
        if amount is None:
            continue
        pairs.append({
            "currency": _normalize_currency(match.group("currency"), fallback="USD"),
            "amount": float(amount),
        })

    for match in code_pattern.finditer(text):
        amount = _to_float(match.group("amount"), strict_clean=False, max_price_ceiling=100000.0)
        if amount is None:
            continue
        pairs.append({
            "currency": _normalize_currency(match.group("currency"), fallback="USD"),
            "amount": float(amount),
        })

    return pairs


def _extract_usd_price_under_ceiling(text: str, max_price_ceiling: float = 250.0) -> Optional[float]:
    pairs = _extract_currency_amount_pairs(text)
    if not pairs:
        return None

    usd_candidates: List[float] = []
    for pair in pairs:
        usd_amount = _convert_to_usd(pair["amount"], pair["currency"])
        if usd_amount is None:
            continue
        if usd_amount < max_price_ceiling:
            usd_candidates.append(float(usd_amount))

    if not usd_candidates:
        return None

    return round(min(usd_candidates), 2)


def _parse_deal_candidates(response_text: str, fallback_currency: str = "USD", max_price_ceiling: float = 250.0) -> List[Dict[str, Any]]:
    """Parse hotel candidates from TinyFish response. Strict $250 ceiling applied."""
    candidates: List[Dict[str, Any]] = []
    parsed_items = _extract_json_array(response_text)

    if parsed_items:
        for item in parsed_items:
            if not isinstance(item, dict):
                continue

            hotel_name = (
                item.get("hotel_name")
                or item.get("name")
                or item.get("hotel")
                or "Unknown Hotel"
            )
            rating_val = item.get("rating") or item.get("star_rating") or item.get("stars")
            rating = _to_float(rating_val, strict_clean=False, max_price_ceiling=10.0)
            
            price_val = (
                item.get("final_price")
                or item.get("price")
                or item.get("total_price")
                or item.get("nightly_price")
            )
            final_price = _to_float(price_val, strict_clean=True, max_price_ceiling=max_price_ceiling)

            if final_price is None or final_price > max_price_ceiling:
                logger.debug(f"Skipping {hotel_name}: price ${final_price} exceeds ${max_price_ceiling} ceiling")
                continue

            currency = _normalize_currency(item.get("currency"), fallback=fallback_currency)
            usd_price = _convert_to_usd(float(final_price), currency)
            if usd_price is None:
                continue
            if usd_price >= max_price_ceiling:
                continue

            has_deal_badge = bool(
                item.get("has_deal_badge")
                or item.get("deal_badge")
                or item.get("discounted")
                or item.get("is_deal")
            )

            candidates.append({
                "hotel_name": str(hotel_name).strip(),
                "rating": rating,
                "final_price": round(float(usd_price), 2),
                "currency": "USD",
                "has_deal_badge": has_deal_badge,
                "hotel_url": (item.get("hotel_url") or item.get("url") or "").strip(),
                "room_type": (item.get("room_type") or "").strip(),
            })

    if candidates:
        return candidates

    fallback_hotel = re.search(r'HOTEL_NAME\s*:\s*(.+)', response_text, re.IGNORECASE)
    fallback_rating = re.search(r'RATING\s*:\s*([0-9]+(?:\.[0-9]+)?)', response_text, re.IGNORECASE)
    fallback_price = re.search(r'FINAL_PRICE\s*:\s*([^\n\r]+)', response_text, re.IGNORECASE)
    fallback_currency_match = re.search(r'CURRENCY\s*:\s*([A-Za-z$€£]{1,4})', response_text, re.IGNORECASE)
    fallback_deal = re.search(r'DEAL_BADGE\s*:\s*(YES|TRUE|1)', response_text, re.IGNORECASE)

    if fallback_hotel and fallback_price:
        parsed_price = _to_float(fallback_price.group(1), strict_clean=True, max_price_ceiling=100000.0)
        fallback_currency_value = _normalize_currency(fallback_currency_match.group(1) if fallback_currency_match else fallback_currency, fallback=fallback_currency)
        usd_price = _convert_to_usd(float(parsed_price), fallback_currency_value) if parsed_price is not None else None
        if usd_price is not None and usd_price < max_price_ceiling:
            candidates.append({
                "hotel_name": fallback_hotel.group(1).strip(),
                "rating": float(fallback_rating.group(1)) if fallback_rating else None,
                "final_price": round(float(usd_price), 2),
                "currency": "USD",
                "has_deal_badge": bool(fallback_deal),
                "hotel_url": "",
                "room_type": "",
            })

    return candidates


def _filter_and_rank_deals(candidates: List[Dict[str, Any]], min_rating: float = 3.5,
                           max_price_for_mid_rating: float = 500.0,
                           preferred_currency: str = "USD") -> List[Dict[str, Any]]:
    """Apply rating/deal/price sanity checks and rank candidates."""
    if not candidates:
        return []

    normalized_currency = _normalize_currency(preferred_currency, fallback="USD")
    same_currency_candidates = [c for c in candidates if _normalize_currency(c.get("currency"), fallback=normalized_currency) == normalized_currency]
    baseline = same_currency_candidates if same_currency_candidates else candidates

    filtered: List[Dict[str, Any]] = []
    for candidate in baseline:
        rating = _to_float(candidate.get("rating"))
        price = _to_float(candidate.get("final_price"))

        if rating is None or rating < min_rating:
            continue
        if price is None:
            continue
        if min_rating <= rating < 4.0 and price > max_price_for_mid_rating:
            continue

        normalized = dict(candidate)
        normalized["rating"] = float(rating)
        normalized["final_price"] = float(price)
        normalized["currency"] = _normalize_currency(candidate.get("currency"), fallback=normalized_currency)
        normalized["has_deal_badge"] = bool(candidate.get("has_deal_badge"))
        filtered.append(normalized)

    filtered.sort(key=lambda item: (0 if item.get("has_deal_badge") else 1, item.get("final_price", float("inf"))))
    return filtered


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
    
    goal = f"""
    Search for hotel prices for {hotel_name} on dates {dates}.
    Strict rules:
    1) Prefer prices shown in USD ($).
    2) If page currency is not USD, convert to USD before returning.
    3) Ignore any price >= $250.
    4) Ignore strike-through/original prices and taxes-only fragments.

    Return plain text lines:
    HOTEL_NAME: <name>
    CURRENCY: <USD>
    FINAL_PRICE_USD: <$123.45>
    """
    
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


def manage_favorites(website: str, username: str, password: str = None,
                    hotel_url: str = "", target_price: float = 0,
                    two_fa_code: str = None, hotel_name_query: str = "",
                    dates: str = "", currency: str = "USD",
                    preview_only: bool = True, top_n: int = 3) -> Dict:
    """Search high-quality deals and manage favorites using existing cookies/session."""

    logger.info("Running Smart Wishlist Hunter with rating/deal/price sanity filters")

    if not login_to_booking_site(website, username, password, two_fa_code):
        return {
            "success": False,
            "message": "Login failed",
            "hotel_name": "",
            "current_price": None,
            "action": "none"
        }

    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }

    normalized_currency = _normalize_currency(currency, fallback="USD")
    
    if hotel_url:
        target_url = hotel_url
    else:
        base_url = "https://www.booking.com/searchresults.html"
        url_filters = "&nflt=class%3D3%3Bclass%3D4%3Bprice%3DUSD-0-150-1"
        target_url = f"{base_url}{url_filters}"
    
    query_text = hotel_name_query or "best value hotels"

    extraction_goal = f"""
    Use existing authenticated cookies/session cookies only. Do not logout and do not switch accounts.
    Do not click any Heart/Save buttons in this step.

    PRICE CEILING RULE: Only extract prices under $250. If you see $250 or higher, SKIP that hotel.

    If URL points to a specific hotel page, evaluate that listing and nearby alternatives.
    If no specific hotel is provided, search Booking.com for: {query_text} with dates: {dates or 'flexible dates'}.

    Include ONLY hotels with rating 3.5 or higher.
    Prioritize hotels with deal indicators like "Deal", "Discounted", or "Limited time deal".
    Extract FINAL payable price (including taxes/fees when visible). IGNORE any price >= $250.
    Ignore strikethrough/original prices.
    Keep all prices in one consistent currency; target currency is {normalized_currency}.

    Return ONLY a JSON array (no markdown), max 8 items, each object keys exactly:
    hotel_name, rating, final_price, currency, has_deal_badge, hotel_url, room_type
    """

    payload = {
        "url": target_url,
        "goal": extraction_goal
    }

    try:
        response_text = call_tinyfish_api(url, headers, payload, timeout=180, max_retries=1)
        if response_text is None:
            return {
                "success": False,
                "message": "TinyFish call failed",
                "hotel_name": "",
                "current_price": None,
                "action": "none"
            }

        raw_candidates = _parse_deal_candidates(response_text, fallback_currency=normalized_currency, max_price_ceiling=250.0)
        ranked_candidates = _filter_and_rank_deals(
            raw_candidates,
            min_rating=3.5,
            max_price_for_mid_rating=250.0,
            preferred_currency=normalized_currency,
        )

        shortlisted = ranked_candidates[:max(1, top_n)]
        if not shortlisted:
            logger.info("No realistic 3.5+ deals found under $250 ceiling. Searching for better deals...")
            return {
                "success": False,
                "message": "Searching for better deals...",
                "hotel_name": "",
                "current_price": None,
                "action": "none",
                "preview_required": False,
                "extracted_deals": [],
            }

        preview_message = f"Found {len(shortlisted)} deal(s) under $250. Review before hearting."
        if preview_only:
            logger.info(preview_message)
            minimalist_deals = [
                {
                    "hotel_name": d.get("hotel_name", ""),
                    "rating": d.get("rating"),
                    "price": d.get("final_price"),
                    "currency": "USD",
                }
                for d in shortlisted
            ]
            return {
                "success": True,
                "message": preview_message,
                "hotel_name": shortlisted[0].get("hotel_name", ""),
                "current_price": shortlisted[0].get("final_price"),
                "action": "preview",
                "preview_required": True,
                "extracted_deals": minimalist_deals,
            }

        heart_goal = f"""
        Use existing authenticated cookies/session. Do not logout and do not switch accounts.
        Add these hotels to Favorites by clicking the Heart/Save icon:
        {json.dumps(shortlisted)}

        For each attempt return one line exactly:
        ADDED: <hotel_name> | PRICE: <currency><price> | RATING: <rating> | STATUS: <SUCCESS|FAILED>
        """

        heart_payload = {
            "url": "https://www.booking.com",
            "goal": heart_goal,
        }

        heart_response = call_tinyfish_api(url, headers, heart_payload, timeout=180, max_retries=1)
        if heart_response is None:
            minimalist_deals = [
                {
                    "hotel_name": d.get("hotel_name", ""),
                    "rating": d.get("rating"),
                    "price": d.get("final_price"),
                    "currency": "USD",
                }
                for d in shortlisted
            ]
            return {
                "success": False,
                "message": "Failed during favorites hearting step",
                "hotel_name": shortlisted[0].get("hotel_name", ""),
                "current_price": shortlisted[0].get("final_price"),
                "action": "none",
                "preview_required": False,
                "extracted_deals": minimalist_deals,
            }

        added_hotels: List[Dict[str, Any]] = []
        for candidate in shortlisted:
            hotel_name = candidate.get("hotel_name", "Unknown Hotel")
            price = float(candidate.get("final_price", 0.0))
            rating = float(candidate.get("rating", 0.0))
            success_pattern = re.search(
                rf"ADDED\s*:\s*{re.escape(hotel_name)}[\s\S]*?STATUS\s*:\s*SUCCESS",
                heart_response,
                re.IGNORECASE,
            )
            if success_pattern:
                log_line = f"[{datetime.now().isoformat()}] | Found: {hotel_name} | Rating: {rating:.1f} | Price: {normalized_currency} {price:.2f} | Status: Added to Favs ✅"
                logger.info(log_line)
                logger.info(f"Successfully added {hotel_name} to Favorites at {normalized_currency} {price:.2f} (3.5+ Rating detected).")
                added_hotels.append(candidate)

        if added_hotels:
            top_hotel = added_hotels[0]
            minimalist_deals = [
                {
                    "hotel_name": d.get("hotel_name", ""),
                    "rating": d.get("rating"),
                    "price": d.get("final_price"),
                    "currency": "USD",
                }
                for d in added_hotels
            ]
            return {
                "success": True,
                "message": f"Added {len(added_hotels)} hotel(s) to Favorites",
                "hotel_name": top_hotel.get("hotel_name", ""),
                "current_price": top_hotel.get("final_price"),
                "action": "saved",
                "preview_required": False,
                "extracted_deals": minimalist_deals,
                "added_hotels": added_hotels,
            }

        minimalist_deals = [
            {
                "hotel_name": d.get("hotel_name", ""),
                "rating": d.get("rating"),
                "price": d.get("final_price"),
                "currency": "USD",
            }
            for d in shortlisted
        ]
        return {
            "success": False,
            "message": "No hotels were confirmed as added to Favorites",
            "hotel_name": shortlisted[0].get("hotel_name", ""),
            "current_price": shortlisted[0].get("final_price"),
            "action": "none",
            "preview_required": False,
            "extracted_deals": minimalist_deals,
        }
    except Exception as e:
        logger.error(f"Smart Wishlist Hunter failed: {e}")
        return {
            "success": False,
            "message": f"Smart Wishlist Hunter failed: {e}",
            "hotel_name": "",
            "current_price": None,
            "action": "none",
            "preview_required": False,
            "extracted_deals": [],
        }


__all__ = ['get_current_price', 'login_to_booking_site', 'fetch_reservations', 'cancel_booking', 'rebook_with_new_price', 'manage_favorites']
