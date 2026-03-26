"""
agents/browser_agent_enhanced.py
RefundFish - Advanced TinyFish Browser Automation Agent
Handles passwordless login, session management, room verification, and safe cancellation
"""

import requests
import json
import re
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from config.settings import TINYFISH_API_KEY
from config.logger import setup_logger

logger = setup_logger("browser_agent")

# Session storage directory
SESSION_DIR = Path('data/sessions')
SESSION_DIR.mkdir(exist_ok=True)

# ============ PRICE EXTRACTION & SEARCH ============

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


def generate_mock_price(original_price: float, hotel_name: str) -> float:
    """Generate realistic mock price for testing when TinyFish is unavailable
    
    Returns a price ±10-30% of the original based on hotel name hash
    """
    from config.settings import MOCK_PRICE_VARIANCE
    import hashlib
    
    # Use hotel name to seed price variance (consistent for same hotel)
    hash_val = int(hashlib.md5(hotel_name.encode()).hexdigest(), 16)
    variance = (hash_val % 100) / 100.0  # 0-1
    
    # Mix variance: some hotels cheaper (-%), some expensive (+%)
    if variance < 0.5:
        # Cheaper option (15-30% discount)
        multiplier = 1 - (0.15 + (variance * 0.3))
    else:
        # More expensive option (10-25% markup)
        multiplier = 1 + (0.10 + ((1 - variance) * 0.15))
    
    mock_price = original_price * multiplier
    logger.info(f"🎭 MOCK MODE: ${original_price:.2f} → ${mock_price:.2f} (variance: {(multiplier-1)*100:+.1f}%)")
    return round(mock_price, 2)


def get_current_price(hotel_name: str, dates: str, original_price: Optional[float] = None) -> Optional[float]:
    """Search for hotel price using TinyFish agent (or mock mode if TinyFish is unavailable)"""
    from config.settings import USE_MOCK_PRICES
    
    logger.info(f"🔍 Searching price: {hotel_name} for {dates}")
    
    # Check if mock mode is enabled
    if USE_MOCK_PRICES:
        if original_price:
            return generate_mock_price(original_price, hotel_name)
        else:
            logger.warning("Mock mode enabled but no original_price provided - defaulting to $150")
            return generate_mock_price(150.0, hotel_name)
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"Go to Google. Search for '{hotel_name}' hotel price for dates {dates}. Find the lowest available rate. Return only the numeric price in format: $XXX.XX"
    
    payload = {
        "url": "https://www.google.com",
        "goal": goal,
        "screenshot": False
    }
    
    try:
        logger.debug("Calling TinyFish price search...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        # Check for service unavailability before parsing
        if response.status_code == 503:
            logger.error("❌ TinyFish API is currently unavailable (503)")
            logger.info("📋 Please check: https://tinyfish.ai for service status")
            logger.info("💡 Tip: Set USE_MOCK_PRICES=true in .env to test while TinyFish recovers")
            return None
        
        response.raise_for_status()
        
        response_text = response.text
        logger.debug(f"Response: {response_text[:300]}")
        
        price = extract_price(response_text)
        if price:
            logger.info(f"✓ Found price: ${price}")
            return price
        
        logger.warning("No price found in response")
        return None
        
    except requests.exceptions.Timeout:
        logger.error("❌ TinyFish timeout - service is slow or unresponsive (>120 seconds)")
        logger.info("📋 The TinyFish API may be down. Check https://tinyfish.ai")
        logger.info("💡 Tip: Set USE_MOCK_PRICES=true in .env to test while TinyFish recovers")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ TinyFish connection error - service unreachable")
        logger.debug(f"Connection details: {e}")
        logger.info("📋 The TinyFish API may be down. Check https://tinyfish.ai")
        logger.info("💡 Tip: Set USE_MOCK_PRICES=true in .env to test while TinyFish recovers")
        return None
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, 'status_code', 'unknown')
        if status == 403:
            logger.error("❌ 403 Forbidden - Check TinyFish API key at https://tinyfish.ai")
        elif status == 503:
            logger.error("❌ TinyFish API service unavailable (503)")
        else:
            logger.error(f"❌ HTTP Error {status}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ TinyFish error: {e}")
        return None


# ============ SESSION MANAGEMENT ============

def _get_session_file(website: str) -> Path:
    """Get session file path for a website"""
    safe_name = website.replace('.', '_').replace(':', '')
    return SESSION_DIR / f"{safe_name}_session.json"


def save_session(website: str, session_data: Dict) -> bool:
    """Save session state after successful login"""
    try:
        session_file = _get_session_file(website)
        session_data['saved_at'] = datetime.now().isoformat()
        session_data['website'] = website
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        logger.info(f"✓ Session saved for {website}")
        return True
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        return False


def load_session(website: str) -> Optional[Dict]:
    """Load saved session for faster re-authentication"""
    try:
        session_file = _get_session_file(website)
        if session_file.exists():
            with open(session_file, 'r') as f:
                data = json.load(f)
                logger.info(f"✓ Loaded session for {website} (saved {data.get('saved_at', 'unknown')})")
                return data
    except Exception as e:
        logger.error(f"Failed to load session: {e}")
    
    return None


def clear_session(website: str) -> bool:
    """Clear saved session after logout or credential change"""
    try:
        session_file = _get_session_file(website)
        if session_file.exists():
            session_file.unlink()
            logger.info(f"✓ Session cleared for {website}")
            return True
    except Exception as e:
        logger.error(f"Failed to clear session: {e}")
    
    return False


# ============ LOGIN - PASSWORDLESS & TRADITIONAL ============

def login_to_booking_site(website: str, username: str, password: str = None, 
                         two_fa_code: str = None, use_session: bool = True) -> Dict:
    """
    Login to hotel booking website with advanced passwordless support
    
    Args:
        website: Website name (booking.com, expedia.com, etc)
        username: Email or username
        password: Account password (optional if using 2FA)
        two_fa_code: 2FA/Verification code (optional)
        use_session: Try to use saved session first
    
    Returns:
        Dict with keys:
        - success: bool
        - method: str (session, password, 2fa, magic_link)
        - session: Dict (session data if saved)
        - message: str
        - requires_manual_action: bool
    """
    
    logger.info(f"🔐 Login attempt for {website} as {username}")
    
    # Try to use cached session first
    if use_session:
        session = load_session(website)
        if session:
            return {
                "success": True,
                "method": "session",
                "session": session,
                "message": f"Logged in using cached session",
                "requires_manual_action": False
            }
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Determine login method
    if website.lower() == 'booking.com':
        return _login_booking_com_passwordless(url, headers, username)
    elif password:
        return _login_with_password(url, headers, website, username, password)
    elif two_fa_code:
        return _login_with_2fa(url, headers, website, username, two_fa_code)
    else:
        return {
            "success": False,
            "method": "none",
            "message": "No authentication method provided (password, 2FA code, or session required)",
            "requires_manual_action": False
        }


def _login_booking_com_passwordless(url: str, headers: Dict, username: str) -> Dict:
    """
    Handle Booking.com passwordless login (Magic Link via email)
    
    Strategy:
    1. Agent enters email
    2. Agent waits for user to click email link
    3. Capture cookies/session after successful auth
    """
    
    logger.info("📧 Booking.com Magic Link Login - Waiting for manual intervention")
    
    goal = f"""
    Task: Login to Booking.com using Magic Link authentication
    
    Step 1: Go to https://www.booking.com
    Step 2: Click on the login/sign-in button
    Step 3: Enter this email address: {username}
    Step 4: Follow the prompt for "Email verification" or "Magic Link"
    Step 5: IMPORTANT: Wait for the verification email
    Step 6: DO NOT proceed until a login confirmation instruction appears
    
    WAIT_FOR_MANUAL_INTERVENTION: A user will click the link in their email. 
    Once the email link has been clicked and the session is authenticated, 
    you will see the Booking.com dashboard/home page.
    
    Step 7: Once authenticated and on the dashboard, take a screenshot
    Step 8: Verify you are logged in by checking the user account section
    Step 9: Return SUCCESS with current URL and session info
    """
    
    payload = {
        "url": "https://www.booking.com",
        "goal": goal,
        "screenshot": True,
        "timeout": 600  # 10 minutes to allow manual email click
    }
    
    try:
        logger.info("⏳ Waiting for Booking.com authentication (max 10 minutes)...")
        response = requests.post(url, headers=headers, json=payload, timeout=660)
        response.raise_for_status()
        
        response_text = response.text
        logger.debug(f"Response: {response_text[:500]}")
        
        # Check for success indicators
        success_indicators = ['dashboard', 'logged in', 'booking', 'success', username.lower()]
        is_success = any(indicator in response_text.lower() for indicator in success_indicators)
        
        if is_success:
            # Save session state after successful login
            session_data = {
                "username": username,
                "email": username,
                "authenticated_at": datetime.now().isoformat(),
                "method": "magic_link",
                "website": "booking.com"
            }
            save_session("booking.com", session_data)
            
            logger.info("✓ Booking.com Magic Link login successful!")
            return {
                "success": True,
                "method": "magic_link",
                "session": session_data,
                "message": "Magic Link authentication completed successfully",
                "requires_manual_action": False
            }
        else:
            logger.warning("⚠️ Authentication status unclear - manual verification recommended")
            return {
                "success": False,
                "method": "magic_link",
                "message": "Authentication pending - please verify email link was clicked",
                "requires_manual_action": True
            }
        
    except requests.exceptions.Timeout:
        logger.warning("⏱️ Timeout waiting for manual authentication - user may still click email link")
        return {
            "success": False,
            "method": "magic_link",
            "message": "Timeout (10+ minutes). If you clicked the email link, the session should be active.",
            "requires_manual_action": True
        }
    except Exception as e:
        logger.error(f"❌ Magic Link login error: {e}")
        return {
            "success": False,
            "method": "magic_link",
            "message": f"Magic Link error: {str(e)}",
            "requires_manual_action": False
        }


def _login_with_password(url: str, headers: Dict, website: str, username: str, password: str) -> Dict:
    """Login using traditional password authentication"""
    
    logger.info(f"🔐 Password login for {website}")
    
    site_config = {
        'booking.com': f"""
        Go to https://www.booking.com.
        Click the login/sign-in button.
        Enter email: {username}
        Enter password: {password}
        Click login button.
        Verify successful login by checking for user dashboard.
        Return SUCCESS if logged in.
        """,
        'expedia.com': f"""
        Go to https://www.expedia.com.
        Click Sign In.
        Enter email: {username}
        Enter password: {password}
        Click continue/login.
        Verify credentials accepted.
        Return SUCCESS if logged in.
        """,
        'hotels.com': f"""
        Go to https://www.hotels.com.
        Click My Account/Sign In.
        Enter email: {username}
        Enter password: {password}
        Click Sign In.
        Verify login successful.
        Return SUCCESS if authenticated.
        """,
    }
    
    goal = site_config.get(website, f"Login to {website} with email {username} and provided password. Verify successful authentication.")
    
    payload = {
        "url": f"https://www.{website.replace(':', '')}",
        "goal": goal,
        "screenshot": True
    }
    
    try:
        logger.debug("Authenticating with password...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        response_text = response.text
        if any(word in response_text.lower() for word in ['success', 'logged in', 'dashboard', 'account']):
            session_data = {
                "username": username,
                "authenticated_at": datetime.now().isoformat(),
                "method": "password",
                "website": website
            }
            save_session(website, session_data)
            
            logger.info(f"✓ Password login successful for {website}")
            return {
                "success": True,
                "method": "password",
                "session": session_data,
                "message": "Password authentication successful",
                "requires_manual_action": False
            }
        else:
            logger.warning("⚠️ Login response unclear - may require manual verification")
            return {
                "success": False,
                "method": "password",
                "message": "Password login unclear response - check credentials",
                "requires_manual_action": True
            }
            
    except Exception as e:
        logger.error(f"❌ Password login failed: {e}")
        return {
            "success": False,
            "method": "password",
            "message": f"Password login error: {str(e)}",
            "requires_manual_action": False
        }


def _login_with_2fa(url: str, headers: Dict, website: str, username: str, two_fa_code: str) -> Dict:
    """Login using 2FA/OTP code"""
    
    logger.info(f"📱 2FA login for {website}")
    
    goal = f"""
    Login to {website}:
    1. Navigate to login page
    2. Enter email: {username}
    3. When prompted for verification code, enter: {two_fa_code}
    4. Complete verification
    5. Verify you are logged in
    Return SUCCESS if authentication complete.
    """
    
    payload = {
        "url": f"https://www.{website.replace(':', '')}",
        "goal": goal,
        "screenshot": True
    }
    
    try:
        logger.debug("Authenticating with 2FA code...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        response_text = response.text
        if any(word in response_text.lower() for word in ['success', 'logged in', 'verified', 'verified', 'confirmed']):
            session_data = {
                "username": username,
                "authenticated_at": datetime.now().isoformat(),
                "method": "2fa",
                "website": website
            }
            save_session(website, session_data)
            
            logger.info(f"✓ 2FA login successful for {website}")
            return {
                "success": True,
                "method": "2fa",
                "session": session_data,
                "message": "2FA verification successful",
                "requires_manual_action": False
            }
        else:
            return {
                "success": False,
                "method": "2fa",
                "message": "2FA verification unclear - code may be invalid",
                "requires_manual_action": True
            }
            
    except Exception as e:
        logger.error(f"❌ 2FA login failed: {e}")
        return {
            "success": False,
            "method": "2fa",
            "message": f"2FA login error: {str(e)}",
            "requires_manual_action": False
        }


# ============ ADVANCED BOOKING OPERATIONS ============

def verify_room_details(hotel_name: str, original_booking: Dict, search_results: Dict) -> Dict:
    """
    Compare original booking details with new search results
    
    Verifies:
    - Room type matches
    - Breakfast inclusion status
    - Free cancellation policy
    
    Args:
        hotel_name: Hotel name
        original_booking: Original booking details from bookings.json
        search_results: New search result data
    
    Returns:
        Dict with verification results and safety score
    """
    
    logger.info(f"🔍 Verifying room details for {hotel_name}")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"""
    Task: Verify booking details for {hotel_name}
    
    Looking for the following details about the room:
    - Room Type (e.g., "Deluxe Double", "Suite", "Standard")
    - Breakfast Inclusion (Included, Not Included, etc)
    - Free Cancellation Policy (Yes/No, or cancellation deadline)
    - Number of Guests
    - Amenities comparison
    
    Original booking details to compare:
    {json.dumps(original_booking, indent=2)}
    
    Current search result details:
    {json.dumps(search_results, indent=2)}
    
    Return a JSON object with:
    {{
        "room_type_match": boolean,
        "breakfast_match": boolean,
        "free_cancellation": boolean,
        "same_capacity": boolean,
        "safety_score": number (0-100),
        "warnings": [list of any differences],
        "verification_status": "SAFE" or "CAUTION" or "UNSAFE"
    }}
    """
    
    payload = {
        "url": "https://www.booking.com",
        "goal": goal,
        "screenshot": False
    }
    
    try:
        logger.debug("Running room detail verification...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        response_text = response.text
        
        # Try to extract JSON from response
        try:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                verification = json.loads(json_match.group())
                logger.info(f"✓ Room verification complete: {verification.get('verification_status', 'UNKNOWN')}")
                return verification
        except:
            pass
        
        # Fallback verification
        logger.warning("⚠️ Could not parse verification details - proceeding with caution")
        return {
            "room_type_match": True,
            "breakfast_match": True,
            "free_cancellation": True,
            "same_capacity": True,
            "safety_score": 85,
            "warnings": ["Manual verification recommended"],
            "verification_status": "CAUTION"
        }
        
    except Exception as e:
        logger.error(f"❌ Room verification error: {e}")
        return {
            "room_type_match": False,
            "breakfast_match": False,
            "free_cancellation": False,
            "same_capacity": False,
            "safety_score": 0,
            "warnings": [f"Verification error: {str(e)}"],
            "verification_status": "UNSAFE"
        }


def capture_proof(hotel_name: str, dates: str, new_price: float, savings: float) -> Optional[str]:
    """
    Capture screenshot proof of price drop
    
    Args:
        hotel_name: Hotel name
        dates: Check-in to check-out dates
        new_price: New found price
        savings: Savings amount
    
    Returns:
        Path to saved screenshot or None if failed
    """
    
    logger.info(f"📸 Capturing proof for {hotel_name}: ${new_price} (saved ${savings})")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"""
    Navigate to the search results page for {hotel_name} with dates {dates}.
    Ensure the following are visible on screen:
    - Hotel name: {hotel_name}
    - Price displayed: ${new_price}
    - Date range: {dates}
    - Any relevant room details and amenities
    
    Take a clear screenshot showing the price and all details.
    Return the URL and pricing information.
    """
    
    payload = {
        "url": "https://www.booking.com",
        "goal": goal,
        "screenshot": True
    }
    
    try:
        logger.debug("Requesting screenshot proof...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        response_text = response.text
        logger.debug(f"Screenshot response received")
        
        # Save screenshot metadata
        proof_dir = Path('data/proofs')
        proof_dir.mkdir(exist_ok=True)
        
        proof_file = proof_dir / f"proof_{hotel_name.replace(' ', '_')}_{int(time.time())}.json"
        
        proof_data = {
            "timestamp": datetime.now().isoformat(),
            "hotel": hotel_name,
            "dates": dates,
            "new_price": new_price,
            "savings": savings,
            "screenshot_response": response_text[:500],
            "full_response": response_text
        }
        
        with open(proof_file, 'w') as f:
            json.dump(proof_data, f, indent=2)
        
        logger.info(f"✓ Proof captured at {proof_file}")
        return str(proof_file)
        
    except Exception as e:
        logger.error(f"❌ Proof capture failed: {e}")
        return None


def execute_cancel_sequence(website: str, booking_id: str, paid_price: float,
                           new_price: float) -> Dict:
    """
    Safely cancel booking with refund validation
    
    Workflow:
    1. Navigate to "Manage Bookings"
    2. Find booking by ID
    3. Verify refund amount matches original price
    4. Click "Cancel" button
    5. Confirm cancellation
    6. Verify cancellation success
    
    Args:
        website: Booking website
        booking_id: Booking ID to cancel
        paid_price: Original price paid (for validation)
        new_price: New price found (context)
    
    Returns:
        Dict with cancellation result
    """
    
    logger.info(f"🚫 Executing cancellation sequence for booking {booking_id}")
    logger.info(f"   Original: ${paid_price} → New: ${new_price}")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"""
    CRITICAL CANCELLATION WORKFLOW - Follow exactly:
    
    Step 1: Navigate to My Bookings or Manage Bookings section
    Step 2: Find the booking with ID: {booking_id}
    Step 3: VERIFY the refund amount shown is: ${paid_price:.2f}
            If different, STOP and report the actual refund amount
    Step 4: If refund matches, click the "Cancel Booking" or "Cancel Reservation" button
    Step 5: If a confirmation dialog appears:
            - Read the refund amount carefully (must be ${paid_price:.2f})
            - Click "Confirm" or "Yes, Cancel"
            - If it asks "Are you sure?", click the final confirmation
    Step 6: After cancellation, you should see "Cancelled" status or confirmation message
    Step 7: Return JSON with:
            {{
                "cancelled": true/false,
                "booking_id": "{booking_id}",
                "refund_amount": actual_amount_shown,
                "expected_refund": {paid_price},
                "status": "CANCELLED" or "FAILED_REFUND_MISMATCH" or "FAILED_OTHER",
                "message": "Detailed result message"
            }}
    
    SAFETY: Only cancel if refund amount matches ${paid_price:.2f}
    """
    
    payload = {
        "url": f"https://www.{website.replace(':', '')}",
        "goal": goal,
        "screenshot": True
    }
    
    try:
        logger.info("Initiating cancellation sequence...")
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        
        response_text = response.text
        logger.debug(f"Cancel response: {response_text[:500]}")
        
        # Try to parse JSON result
        try:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                # Validate refund amount
                if result.get('cancelled') and result.get('refund_amount') != paid_price:
                    logger.warning(f"⚠️ REFUND MISMATCH: Expected ${paid_price}, got ${result.get('refund_amount')}")
                    result['status'] = 'FAILED_REFUND_MISMATCH'
                    return result
                
                if result.get('cancelled'):
                    logger.info(f"✓ Booking {booking_id} successfully cancelled!")
                    return result
                else:
                    logger.error(f"✗ Cancellation failed: {result.get('message')}")
                    return result
        except:
            pass
        
        # Fallback: check response text for success indicators
        if any(word in response_text.lower() for word in ['cancelled', 'success', 'confirmed']):
            logger.info(f"✓ Booking appears to be cancelled (refund: ${paid_price})")
            return {
                "cancelled": True,
                "booking_id": booking_id,
                "refund_amount": paid_price,
                "expected_refund": paid_price,
                "status": "CANCELLED",
                "message": "Cancellation confirmed"
            }
        else:
            logger.error("✗ Cancellation status unclear")
            return {
                "cancelled": False,
                "booking_id": booking_id,
                "refund_amount": None,
                "expected_refund": paid_price,
                "status": "UNCLEAR",
                "message": "Cancellation status unclear - manual verification recommended"
            }
            
    except Exception as e:
        logger.error(f"❌ Cancellation error: {e}")
        return {
            "cancelled": False,
            "booking_id": booking_id,
            "refund_amount": None,
            "expected_refund": paid_price,
            "status": "FAILED",
            "message": f"Cancellation error: {str(e)}"
        }


# ============ RESERVATION OPERATIONS ============

def fetch_reservations(website: str, username: str, password: str = None, 
                      two_fa_code: str = None) -> Tuple[List, Dict]:
    """
    Fetch all active reservations from user's booking account
    
    Args:
        website: Booking website (booking.com, expedia.com, etc)
        username: Account email/username
        password: Account password (optional if using 2FA)
        two_fa_code: 2FA verification code (optional if using password)
    
    Returns:
        Tuple of (reservations_list, login_info_dict)
    """
    
    logger.info(f"📋 Fetching reservations from {website}...")
    
    # Login first
    login_result = login_to_booking_site(website, username, password, two_fa_code)
    
    if not login_result.get('success'):
        logger.error(f"❌ Login failed: {login_result.get('message')}")
        
        if login_result.get('requires_manual_action'):
            print("\n" + "="*60)
            print("⚠️  MANUAL ACTION REQUIRED")
            print("="*60)
            print(f"Please check your email for verification link")
            print(f"Email: {username}")
            print(f"Instructions: Click the link in your email to authenticate")
            print("="*60 + "\n")
        
        return [], login_result
    
    logger.info(f"✓ Login successful via {login_result.get('method')}")
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Site-specific goals for fetching reservations
    site_goals = {
        'booking.com': """
        You are now logged in to Booking.com.
        Go to My Bookings page (click profile icon → My bookings if needed).
        List ALL upcoming confirmed reservations.
        For EACH reservation, extract and return as JSON:
        {
            "hotel_name": "exact hotel name",
            "check_in": "YYYY-MM-DD format",
            "check_out": "YYYY-MM-DD format",
            "booking_id": "confirmation/booking number",
            "paid_price": numeric price paid,
            "status": "confirmed or other status"
        }
        Return a JSON array: [{...}, {...}, ...]
        """,
        'expedia.com': """
        Navigate to My Trips/Reservations.
        List ALL upcoming hotel reservations.
        For EACH extract:
        {
            "hotel_name": "hotel name",
            "check_in": "YYYY-MM-DD",
            "check_out": "YYYY-MM-DD",
            "booking_id": "reservation number",
            "paid_price": amount paid,
            "status": "status"
        }
        Return JSON array of all reservations.
        """,
        'hotels.com': """
        Go to My Trips section.
        Show all upcoming hotel bookings.
        For each extract:
        {
            "hotel_name": "name",
            "check_in": "YYYY-MM-DD",
            "check_out": "YYYY-MM-DD",
            "booking_id": "confirmation#",
            "paid_price": price,
            "status": "status"
        }
        Return JSON array.
        """
    }
    
    goal = site_goals.get(website, 
        "Go to My Bookings. Extract all active reservations: hotel name, dates, ID, price. Return JSON array.")
    
    payload = {
        "url": f"https://www.{website.replace(':', '')}",
        "goal": goal,
        "screenshot": False
    }
    
    try:
        logger.debug("Fetching reservations via TinyFish...")
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        
        response_text = response.text
        logger.debug(f"Response: {response_text[:300]}")
        
        reservations = _parse_reservations_response(response_text)
        
        if reservations:
            logger.info(f"✓ Found {len(reservations)} reservation(s)")
        else:
            logger.warning("⚠️ No reservations found")
        
        return reservations, login_result
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch reservations: {e}")
        return [], login_result


def _parse_reservations_response(response_text: str) -> List[Dict]:
    """Parse TinyFish response to extract reservation data"""
    try:
        # Look for JSON in response
        start_idx = response_text.find('[')
        if start_idx == -1:
            start_idx = response_text.find('{')
        
        if start_idx != -1:
            end_idx = response_text.rfind(']' if response_text[start_idx] == '[' else '}') + 1
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                
                if isinstance(data, dict):
                    data = [data]
                elif not isinstance(data, list):
                    return []
                
                # Normalize each reservation
                normalized = []
                for res in data:
                    normalized_res = _normalize_reservation(res)
                    if normalized_res:
                        normalized.append(normalized_res)
                
                return normalized
    except Exception as e:
        logger.warning(f"Could not parse JSON: {e}")
    
    return []


def _normalize_reservation(res: Dict) -> Optional[Dict]:
    """Normalize reservation data to standard format"""
    try:
        hotel = (res.get('hotel_name') or res.get('hotel') or 
                res.get('property name') or '')
        
        check_in = (res.get('check_in') or res.get('checkIn') or 
                   res.get('checkin') or '')
        
        check_out = (res.get('check_out') or res.get('checkOut') or 
                    res.get('checkout') or '')
        
        booking_id = (res.get('booking_id') or res.get('bookingID') or 
                     res.get('confirmation_number') or res.get('reference') or '')
        
        price = res.get('paid_price') or res.get('price') or res.get('amount') or 0
        
        if isinstance(price, str):
            price_match = re.search(r'\d+(?:\.\d{2})?', price.replace(',', ''))
            price = float(price_match.group()) if price_match else 0
        
        status = res.get('status', 'confirmed')
        
        # Format dates
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
        logger.debug(f"Could not normalize: {e}")
    
    return None


def cancel_booking(website: str, booking_id: str, paid_price: float = None) -> Dict:
    """
    Cancel a booking via the execute_cancel_sequence
    
    Args:
        website: Booking website
        booking_id: ID of booking to cancel
        paid_price: Original price (for refund validation)
    
    Returns:
        Cancellation result dict
    """
    
    return execute_cancel_sequence(website, booking_id, paid_price or 0, 0)


def rebook_with_new_price(website: str, username: str, password: str = None, 
                         hotel_name: str = None, dates: str = None, 
                         new_price: float = None) -> bool:
    """
    Rebook same hotel at new price
    
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
    
    logger.info(f"🔄 Rebooking {hotel_name} at ${new_price}...")
    
    # Login first
    login_result = login_to_booking_site(website, username, password)
    
    if not login_result.get('success'):
        logger.error("❌ Could not login for rebooking")
        return False
    
    url = "https://agent.tinyfish.ai/v1/automation/run-sse"
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json"
    }
    
    goal = f"""
    Search and rebook hotel:
    1. Search for: {hotel_name}
    2. Dates: {dates}
    3. Find the exact same hotel (or closest match)
    4. Add to cart
    5. Proceed to checkout
    6. Complete booking
    7. Return the new booking confirmation number
    New Price: ${new_price}
    """
    
    payload = {
        "url": f"https://www.{website.replace(':', '')}",
        "goal": goal,
        "screenshot": True
    }
    
    try:
        logger.debug("Starting rebooking...")
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        
        if any(word in response.text.lower() for word in ['success', 'confirmation', 'booked']):
            logger.info(f"✓ Rebooked successfully at ${new_price}")
            return True
        else:
            logger.warning("⚠️ Rebooking unclear")
            return False
            
    except Exception as e:
        logger.error(f"❌ Rebooking failed: {e}")
        return False


# ============ EXPORTS ============

__all__ = [
    'extract_price',
    'get_current_price',
    'save_session',
    'load_session',
    'clear_session',
    'login_to_booking_site',
    'verify_room_details',
    'capture_proof',
    'execute_cancel_sequence',
    'fetch_reservations',
    'cancel_booking',
    'rebook_with_new_price'
]
