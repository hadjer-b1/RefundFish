"""
RefundFish Web Application - Enhanced Version
Flask backend with advanced TinyFish integration:
- Passwordless login support
- Room verification
- Proof capture
- Safe cancellation with validation
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
from pathlib import Path
from agents.browser_agent_enhanced import (
    get_current_price,
    login_to_booking_site,
    fetch_reservations,
    cancel_booking,
    rebook_with_new_price,
    verify_room_details,
    capture_proof,
    execute_cancel_sequence,
    load_session,
    clear_session
)
from agents.logic_agent import evaluate_refund_opportunity, get_detailed_analysis
from config.logger import setup_logger
import threading
from datetime import datetime
from utils.credentials import credentials_manager

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

logger = setup_logger("web_app")

# Data storage
SEARCH_HISTORY = []
SETTINGS_FILE = Path('data/settings.json')
BOOKINGS_FILE = Path('data/bookings.json')

def load_settings():
    """Load user settings"""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE) as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
    
    return {
        "min_savings_threshold": 10,
        "selected_website": "booking.com",
        "refund_enabled": True,
        "auto_refund": False,
        "require_room_verification": True,
        "auto_capture_proof": True,
        "safe_cancel_mode": True
    }


def save_settings(settings):
    """Save user settings"""
    try:
        SETTINGS_FILE.parent.mkdir(exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        logger.info("Settings saved")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


def load_bookings():
    """Load original bookings reference"""
    try:
        if BOOKINGS_FILE.exists():
            with open(BOOKINGS_FILE) as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading bookings: {e}")
    
    return []


@app.route('/')
def index():
    """Serve main HTML UI"""
    return render_template('index.html')


@app.route('/api/status')
def status():
    """Get system status"""
    from config.settings import TINYFISH_API_KEY
    
    api_configured = bool(TINYFISH_API_KEY)
    
    return jsonify({
        "status": "running",
        "api_configured": api_configured,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def settings_endpoint():
    """Get or update settings"""
    if request.method == 'POST':
        data = request.json
        save_settings(data)
        return jsonify({"status": "saved", "settings": data})
    
    return jsonify(load_settings())


@app.route('/api/search', methods=['POST'])
def search_hotel():
    """Search for hotel price and analyze refund opportunity"""
    data = request.json
    hotel_name = data.get('hotel_name')
    dates = data.get('dates')
    paid_price = float(data.get('paid_price', 0))
    booking_id = data.get('booking_id', '')
    
    if not all([hotel_name, dates, paid_price]):
        return jsonify({"error": "Missing required fields"}), 400
    
    settings = load_settings()
    
    try:
        logger.info(f"🔍 Searching: {hotel_name} for {dates}")
        current_price = get_current_price(hotel_name, dates)
        
        if current_price is None:
            return jsonify({
                "error": "Could not fetch price - TinyFish timeout or error",
                "status": "failed",
                "hotel": hotel_name,
                "dates": dates
            }), 500
        
        # Step 1: Analyze refund opportunity
        should_rebook, savings = evaluate_refund_opportunity(current_price, paid_price)
        analysis = get_detailed_analysis(current_price, paid_price)
        
        # Step 2: Check threshold
        meets_threshold = savings >= settings['min_savings_threshold']
        recommend_refund = should_rebook and meets_threshold
        
        result = {
            "status": "success",
            "hotel": hotel_name,
            "dates": dates,
            "paid_price": paid_price,
            "current_price": current_price,
            "gross_savings": analysis['gross_savings'],
            "savings_percent": analysis['savings_percent'],
            "net_savings": savings,
            "meets_threshold": meets_threshold,
            "threshold": settings['min_savings_threshold'],
            "recommendation": "REBOOK" if recommend_refund else "KEEP CURRENT",
            "auto_refund_status": "pending",
            "verification_status": "pending",
            "proof_captured": False,
            "timestamp": datetime.now().isoformat()
        }
        
        # Step 3: ROOM VERIFICATION (if enabled)
        if recommend_refund and settings.get('require_room_verification', True):
            logger.info("🔍 Verifying room details...")
            bookings = load_bookings()
            original_booking = next(
                (b for b in bookings if b.get('hotel_name') == hotel_name), 
                None
            )
            
            if original_booking:
                search_results = {
                    "hotel_name": hotel_name,
                    "dates": dates,
                    "price": current_price
                }
                
                verification = verify_room_details(
                    hotel_name,
                    original_booking,
                    search_results
                )
                
                result['verification'] = verification
                result['verification_status'] = verification.get('verification_status', 'UNKNOWN')
                
                if verification.get('verification_status') != 'SAFE':
                    logger.warning(f"⚠️ Room verification: {verification.get('verification_status')}")
                    recommend_refund = False  # Don't auto-refund if room is unsafe
            else:
                logger.warning("No original booking found for comparison")
                result['verification_status'] = 'no_original_booking'
        
        # Step 4: AUTO-REFUND LOGIC (if enabled AND verified)
        if recommend_refund and settings.get('auto_refund', False):
            logger.info("💰 Auto-refund trigger activated")
            result["auto_refund_status"] = "processing"
            
            website = settings.get('selected_website', 'booking.com')
            creds = credentials_manager.get_credentials_for_agent(website)
            
            if not creds:
                logger.warning(f"No credentials for {website}")
                result["auto_refund_status"] = "no_credentials"
                result["message"] = f"Add credentials for {website} to enable auto-refund"
            else:
                username = creds.get('username')
                password = creds.get('password')
                two_fa_code = creds.get('two_fa_code')
                
                try:
                    # Step 4a: LOGIN
                    logger.info("🔐 Step 1: Logging in...")
                    login_result = login_to_booking_site(
                        website, username, password, two_fa_code
                    )
                    
                    if not login_result.get('success'):
                        logger.error(f"Login failed: {login_result.get('message')}")
                        
                        if login_result.get('requires_manual_action'):
                            result["auto_refund_status"] = "requires_manual_action"
                            result["message"] = (
                                "🔐 Magic Link Authentication Required\\n"
                                f"Check email: {username}\\n"
                                "Click the verification link to authenticate.\\n"
                                "Then try the search again."
                            )
                            print("\n" + "="*70)
                            print("🔐 MANUAL AUTHENTICATION REQUIRED")
                            print("="*70)
                            print(f"An email was sent to: {username}")
                            print(f"Please open your email and click the verification link.")
                            print(f"Then return here and try the search again.")
                            print("="*70 + "\n")
                        else:
                            result["auto_refund_status"] = "login_failed"
                            result["message"] = f"Login failed: {login_result.get('message')}"
                    else:
                        logger.info("✓ Login successful")
                        
                        # Step 4b: CAPTURE PROOF (if enabled)
                        if settings.get('auto_capture_proof', True):
                            logger.info("📸 Step 2: Capturing proof...")
                            proof_file = capture_proof(
                                hotel_name, dates, current_price, savings
                            )
                            result["proof_captured"] = proof_file is not None
                            result["proof_file"] = proof_file
                            logger.info(f"Proof: {proof_file}")
                        
                        # Step 4c: CANCEL EXISTING BOOKING
                        if booking_id and settings.get('safe_cancel_mode', True):
                            logger.info(f"🚫 Step 3: Cancelling booking {booking_id}...")
                            
                            cancel_result = execute_cancel_sequence(
                                website, booking_id, paid_price, current_price
                            )
                            
                            result["cancel_result"] = cancel_result
                            
                            if cancel_result.get('cancelled'):
                                logger.info(f"✓ Booking cancelled, refund: ${cancel_result.get('refund_amount')}")
                                
                                # Step 4d: REBOOK AT NEW PRICE
                                logger.info(f"🔄 Step 4: Rebooking at ${current_price}...")
                                rebook_success = rebook_with_new_price(
                                    website, username, password, hotel_name, dates, current_price
                                )
                                
                                if rebook_success:
                                    logger.info(f"✓ Rebooked! Saved ${savings:.2f} 🎉")
                                    result["auto_refund_status"] = "success"
                                    result["message"] = f"✓ Auto-refund complete! Saved ${savings:.2f} 🎉"
                                else:
                                    logger.error("Rebooking failed")
                                    result["auto_refund_status"] = "rebook_failed"
                                    result["message"] = "Rebooking failed - refund not applied, manual intervention needed"
                            else:
                                logger.error(f"Cancellation failed: {cancel_result.get('status')}")
                                result["auto_refund_status"] = "cancel_failed"
                                result["message"] = f"Cancellation failed: {cancel_result.get('message')}"
                        else:
                            logger.info("No booking ID or safe cancel mode disabled")
                            result["auto_refund_status"] = "manual_action_needed"
                            result["message"] = "Please manually cancel and rebook"
                
                except Exception as e:
                    logger.error(f"Auto-refund error: {e}")
                    result["auto_refund_status"] = "error"
                    result["message"] = f"Error: {str(e)}"
        
        # Add to search history
        SEARCH_HISTORY.append(result)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route('/api/fetch-reservations', methods=['POST'])
def api_fetch_reservations():
    """Fetch all active reservations from user's booking account"""
    data = request.json
    website = data.get('website', 'booking.com')
    
    try:
        # Get saved credentials
        creds = credentials_manager.get_credentials_for_agent(website)
        
        if not creds:
            return jsonify({
                "status": "error",
                "error": f"No saved credentials for {website}. Please save login credentials first.",
                "reservations": [],
                "count": 0
            }), 400
        
        username = creds.get('username')
        password = creds.get('password')
        two_fa_code = creds.get('two_fa_code')
        email = creds.get('email') or username
        
        logger.info(f"Fetching reservations for {website}...")
        
        # Fetch reservations
        reservations, login_info = fetch_reservations(
            website, username, password, two_fa_code
        )
        
        if not login_info.get('success') and login_info.get('requires_manual_action'):
            print("\n" + "="*70)
            print("📧 MAGIC LINK AUTHENTICATION NEEDED")
            print("="*70)
            print(f"An email was sent to: {email}")
            print("Please click the verification link in your email.")
            print("Then retry fetching your reservations.")
            print("="*70 + "\n")
            
            return jsonify({
                "status": "requires_action",
                "error": f"Please verify your email ({email}) by clicking the link sent to you",
                "reservations": [],
                "count": 0,
                "login_method": login_info.get('method'),
                "requires_manual_action": True
            }), 400
        
        if not login_info.get('success'):
            return jsonify({
                "status": "error",
                "error": f"Login failed: {login_info.get('message')}",
                "reservations": [],
                "count": 0
            }), 500
        
        return jsonify({
            "status": "success",
            "reservations": reservations,
            "count": len(reservations),
            "website": website,
            "login_method": login_info.get('method')
        })
        
    except Exception as e:
        logger.error(f"Error fetching reservations: {e}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "reservations": [],
            "count": 0
        }), 500


@app.route('/api/verify-room', methods=['POST'])
def api_verify_room():
    """Manually verify room details"""
    data = request.json
    hotel_name = data.get('hotel_name')
    original_booking = data.get('original_booking', {})
    search_results = data.get('search_results', {})
    
    if not hotel_name:
        return jsonify({"error": "Missing hotel_name"}), 400
    
    try:
        logger.info(f"Verifying room details for {hotel_name}")
        
        verification = verify_room_details(
            hotel_name, original_booking, search_results
        )
        
        return jsonify(verification)
        
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route('/api/capture-proof', methods=['POST'])
def api_capture_proof():
    """Capture screenshot proof of price"""
    data = request.json
    hotel_name = data.get('hotel_name')
    dates = data.get('dates')
    price = float(data.get('price', 0))
    savings = float(data.get('savings', 0))
    
    if not all([hotel_name, dates, price]):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        logger.info(f"Capturing proof for {hotel_name}")
        
        proof_file = capture_proof(hotel_name, dates, price, savings)
        
        return jsonify({
            "success": proof_file is not None,
            "proof_file": proof_file,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Proof capture error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/cancel-booking', methods=['POST'])
def api_cancel_booking():
    """Cancel a booking with safe verification"""
    data = request.json
    website = data.get('website', 'booking.com')
    booking_id = data.get('booking_id')
    paid_price = float(data.get('paid_price', 0))
    new_price = float(data.get('new_price', 0))
    
    if not booking_id:
        return jsonify({"error": "Missing booking_id"}), 400
    
    try:
        # Get credentials for login
        creds = credentials_manager.get_credentials_for_agent(website)
        if not creds:
            return jsonify({
                "error": f"No credentials for {website}",
                "cancelled": False
            }), 400
        
        username = creds.get('username')
        password = creds.get('password')
        two_fa_code = creds.get('two_fa_code')
        
        # Login first
        logger.info(f"Logging in for cancellation...")
        login_result = login_to_booking_site(website, username, password, two_fa_code)
        
        if not login_result.get('success'):
            return jsonify({
                "error": f"Could not login: {login_result.get('message')}",
                "cancelled": False,
                "requires_manual_action": login_result.get('requires_manual_action', False)
            }), 500
        
        # Execute cancellation
        logger.info(f"Executing cancellation for booking {booking_id}")
        cancel_result = execute_cancel_sequence(
            website, booking_id, paid_price, new_price
        )
        
        return jsonify(cancel_result)
        
    except Exception as e:
        logger.error(f"Cancellation error: {e}")
        return jsonify({"error": str(e), "cancelled": False}), 500


@app.route('/api/history')
def api_history():
    """Get search history"""
    return jsonify(SEARCH_HISTORY)


@app.route('/api/clear-history', methods=['POST'])
def api_clear_history():
    """Clear search history"""
    global SEARCH_HISTORY
    SEARCH_HISTORY = []
    logger.info("Search history cleared")
    return jsonify({"status": "cleared"})


# ============ CREDENTIALS ENDPOINTS ============

@app.route('/api/credentials/list')
def list_credentials():
    """List all saved credentials (without passwords)"""
    try:
        credentials = credentials_manager.list_credentials_safe()
        return jsonify({"credentials": credentials})
    except Exception as e:
        logger.error(f"Error listing credentials: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/credentials/save', methods=['POST'])
def save_credentials():
    """Save new credentials"""
    try:
        data = request.json
        website = data.get('website')
        username = data.get('username')
        password = data.get('password')
        two_fa_code = data.get('two_fa_code')
        
        if not website or not username:
            return jsonify({"error": "Website and username required"}), 400
        
        # Clear old session when saving new credentials
        clear_session(website)
        
        credentials_manager.save_credentials(
            website, username, password, two_fa_code, username
        )
        
        logger.info(f"Saved credentials for {website}")
        return jsonify({"status": "saved", "website": website})
        
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/credentials/delete/<website>', methods=['DELETE'])
def delete_credentials(website):
    """Delete credentials for a website"""
    try:
        credentials_manager.delete_credentials(website)
        clear_session(website)
        logger.info(f"Deleted credentials for {website}")
        return jsonify({"status": "deleted"})
    except Exception as e:
        logger.error(f"Error deleting credentials: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/session/<website>', methods=['GET'])
def check_session(website):
    """Check if user has an active session"""
    session = load_session(website)
    
    return jsonify({
        "has_session": session is not None,
        "session": session,
        "website": website
    })


@app.route('/api/session/<website>', methods=['DELETE'])
def clear_user_session(website):
    """Clear user session"""
    clear_session(website)
    return jsonify({"status": "cleared"})


if __name__ == '__main__':
    logger.info("🚀 Starting RefundFish Web Server")
    app.run(debug=False, host='127.0.0.1', port=5000)
