"""
RefundFish Web Application
Flask backend serving HTML UI with real-time TinyFish integration
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
from pathlib import Path
from agents.browser_agent import get_current_price, login_to_booking_site, fetch_reservations, cancel_booking, rebook_with_new_price
from agents.logic_agent import evaluate_refund_opportunity, get_detailed_analysis
from config.logger import setup_logger
import threading
from datetime import datetime
from utils.credentials import credentials_manager

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

logger = setup_logger("web_app")

# Store search history and settings
SEARCH_HISTORY = []
SETTINGS_FILE = Path('data/settings.json')

def load_settings():
    """Load user settings"""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE) as f:
                return json.load(f)
    except:
        pass
    return {
        "min_savings_threshold": 10,
        "selected_website": "booking.com",
        "refund_enabled": True,
        "auto_refund": False
    }

def save_settings(settings):
    """Save user settings"""
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

@app.route('/')
def index():
    """Serve main HTML UI"""
    return render_template('index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
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
    booking_id = data.get('booking_id', '')  # Optional: for cancellation
    
    if not all([hotel_name, dates, paid_price]):
        return jsonify({"error": "Missing required fields"}), 400
    
    settings = load_settings()
    
    try:
        # Step 1: Search for current price
        logger.info(f"Searching: {hotel_name} for {dates}")
        current_price = get_current_price(hotel_name, dates)
        
        if current_price is None:
            return jsonify({
                "error": "Could not fetch price - TinyFish timeout or API issue",
                "status": "failed",
                "hotel": hotel_name,
                "dates": dates
            }), 500
        
        # Step 2: Analyze refund opportunity
        should_rebook, savings = evaluate_refund_opportunity(current_price, paid_price)
        analysis = get_detailed_analysis(current_price, paid_price)
        
        # Step 3: Apply settings threshold
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
            "timestamp": datetime.now().isoformat()
        }
        
        # Step 4: AUTO-REFUND LOGIC (if enabled and meets threshold)
        if recommend_refund and settings.get('auto_refund', False):
            logger.info("🔄 Auto-refund enabled - initiating automatic rebooking...")
            result["auto_refund_status"] = "processing"
            
            website = settings.get('selected_website', 'booking.com')
            
            # Get saved credentials for this website
            creds = credentials_manager.get_credentials_for_agent(website)
            
            if creds:
                logger.info(f"Found credentials for {website}")
                username = creds.get('username')
                password = creds.get('password')
                two_fa_code = creds.get('two_fa_code')
                email = creds.get('email')
                auth_method = "2FA" if two_fa_code else "Password"
                
                try:
                    # Execute auto-refund workflow
                    logger.info(f"Step 1: Logging in to account (using {auth_method})...")
                    if login_to_booking_site(website, username, password, two_fa_code):
                        logger.info("✓ Login successful")
                        
                        if booking_id:
                            logger.info(f"Step 2: Cancelling booking {booking_id}...")
                            if cancel_booking(website, username, password, booking_id):
                                logger.info("✓ Booking cancelled")
                                
                                logger.info(f"Step 3: Rebooking at new price ${current_price}...")
                                if rebook_with_new_price(website, username, password, hotel_name, dates, current_price):
                                    logger.info(f"✓ Successfully rebooked! Saved ${savings:.2f}")
                                    result["auto_refund_status"] = "success"
                                    result["message"] = f"✓ Auto-refund complete! Saved ${savings:.2f} 🎉"
                                else:
                                    logger.error("Rebooking failed")
                                    result["auto_refund_status"] = "rebook_failed"
                                    result["message"] = "Rebooking failed - check manually"
                            else:
                                logger.error("Cancellation failed")
                                result["auto_refund_status"] = "cancel_failed"
                                result["message"] = "Cancellation failed - check account"
                        else:
                            logger.warning("No booking ID provided for cancellation")
                            result["auto_refund_status"] = "no_booking_id"
                            result["message"] = "Set booking ID to enable auto-cancellation"
                    else:
                        logger.error("Login failed")
                        result["auto_refund_status"] = "login_failed"
                        result["message"] = "Could not login - verify credentials"
                        
                except Exception as e:
                    logger.error(f"Auto-refund error: {e}")
                    result["auto_refund_status"] = "error"
                    result["message"] = f"Auto-refund error: {str(e)}"
            else:
                logger.warning(f"No saved credentials for {website}")
                result["auto_refund_status"] = "no_credentials"
                result["message"] = f"Add credentials for {website} to enable auto-refund"
        
        # Add to search history
        SEARCH_HISTORY.append(result)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route('/api/fetch-reservations', methods=['POST'])
def api_fetch_reservations():
    """
    Fetch all active reservations from user's booking account
    Requires credentials to be saved first
    """
    data = request.json
    website = data.get('website', 'booking.com')
    
    try:
        # Get saved credentials for this website
        creds = credentials_manager.get_credentials_for_agent(website)
        
        if not creds:
            return jsonify({
                "status": "error",
                "error": f"No saved credentials for {website}. Please save your login credentials first.",
                "reservations": []
            }), 400
        
        username = creds.get('username')
        password = creds.get('password')
        two_fa_code = creds.get('two_fa_code')
        
        # Check that we have username (email/password optional, allows Booking.com Magic Link)
        if not username:
            return jsonify({
                "status": "error",
                "error": "Email/username required. Please save your credentials again.",
                "reservations": []
            }), 400
        
        logger.info(f"Fetching reservations for {website}...")
        if two_fa_code:
            auth_method = "2FA Code"
        elif password:
            auth_method = "Password"
        else:
            auth_method = "Magic Link (email)"
            # Print guidance for Magic Link authentication
            print("\n" + "="*70)
            print("📧 MAGIC LINK AUTHENTICATION NEEDED")
            print("="*70)
            print(f"Email: {username}")
            print("\nBefore fetching reservations, you need to authenticate:")
            print("1. Open https://www.booking.com in your browser")
            print("2. Click 'Sign in'")
            print(f"3. Enter your email: {username}")
            print("4. Look for the 'Email verification' or 'Magic Link' option")
            print("5. Check your email for a verification link from Booking.com")
            print("6. Click the link in your email to complete authentication")
            print("7. Return here and try to fetch reservations again")
            print("="*70 + "\n")
            
        logger.info(f"Using {auth_method} authentication")
        
        # Fetch reservations using the browser agent
        reservations = fetch_reservations(website, username, password, two_fa_code)
        
        if reservations:
            logger.info(f"✓ Found {len(reservations)} reservation(s)")
            return jsonify({
                "status": "success",
                "count": len(reservations),
                "reservations": reservations
            })
        else:
            return jsonify({
                "status": "no_reservations",
                "error": "No active reservations found. Check your account manually.",
                "reservations": []
            }), 200
        
    except Exception as e:
        logger.error(f"Error fetching reservations: {e}")
        return jsonify({
            "status": "error",
            "error": f"Failed to fetch reservations: {str(e)}",
            "reservations": []
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get search history"""
    return jsonify(SEARCH_HISTORY)

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Clear search history"""
    global SEARCH_HISTORY
    SEARCH_HISTORY = []
    return jsonify({"status": "cleared"})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get system status"""
    from config.settings import TINYFISH_API_KEY
    
    api_key_valid = TINYFISH_API_KEY and TINYFISH_API_KEY.startswith('sk-tinyfish-')
    
    return jsonify({
        "api_configured": api_key_valid,
        "searches_completed": len(SEARCH_HISTORY),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/credentials/save', methods=['POST'])
def save_credentials():
    """Save encrypted credentials for a website (supports email, password, or 2FA code)"""
    try:
        data = request.json
        website = data.get('website')
        username = data.get('username')
        password = data.get('password')
        two_fa_code = data.get('two_fa_code')
        
        if not all([website, username]):
            return jsonify({"error": "Missing website or username"}), 400
        
        # Allow email-only save (for Booking.com Magic Link), password, or 2FA
        credentials_manager.save_credentials(website, username, password, two_fa_code)
        
        auth_method = "Email only"
        if two_fa_code:
            auth_method = "2FA Code"
        elif password:
            auth_method = "Password"
        
        logger.info(f"Credentials saved for {website} ({auth_method})")
        
        return jsonify({
            "status": "success",
            "message": f"Credentials saved for {website}",
            "website": website,
            "username": username,
            "auth_method": auth_method
        })
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/credentials/list', methods=['GET'])
def list_credentials():
    """List all saved websites with credentials (passwords not returned)"""
    try:
        websites = credentials_manager.list_saved_websites()
        
        creds_list = []
        for website in websites:
            cred = credentials_manager.get_credentials(website)
            if cred:
                creds_list.append({
                    "website": website,
                    "username": cred.get('username')
                    # Password NOT returned for security
                })
        
        return jsonify({"credentials": creds_list})
    except Exception as e:
        logger.error(f"Failed to list credentials: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/credentials/delete/<website>', methods=['DELETE'])
def delete_credentials(website):
    """Delete credentials for a website"""
    try:
        success = credentials_manager.delete_credentials(website)
        if success:
            logger.info(f"Credentials deleted for {website}")
            return jsonify({"status": "success", "message": f"Credentials deleted for {website}"})
        else:
            return jsonify({"error": "No credentials found for this website"}), 404
    except Exception as e:
        logger.error(f"Failed to delete credentials: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting RefundFish Web UI on http://localhost:5000")
    app.run(debug=False, host='localhost', port=5000, use_reloader=False)
