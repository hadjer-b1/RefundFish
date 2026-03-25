"""
RefundFish Web Application
Flask backend serving HTML UI with real-time TinyFish integration
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
from pathlib import Path
import smtplib
from email.message import EmailMessage
import requests
from agents.browser_agent import get_current_price, login_to_booking_site, fetch_reservations, cancel_booking, rebook_with_new_price
from agents.logic_agent import evaluate_refund_opportunity, get_detailed_analysis
from config.logger import setup_logger
import threading
from datetime import datetime, timedelta
from utils.credentials import credentials_manager

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

logger = setup_logger("web_app")

# Store search history and settings
SEARCH_HISTORY = []
SETTINGS_FILE = Path('data/settings.json')
ACTIVITY_LOG_FILE = Path('logs/activity.log')
MONITOR_INTERVAL_SECONDS = 60 * 60
MONITOR_STOP_EVENT = threading.Event()
MONITORING_STATE = {
    "enabled": False,
    "target": None,
    "last_run": None,
    "next_run": None,
    "thread": None
}


def write_activity_log(entry: dict):
    """Persist activity entry to file and logger."""
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ACTIVITY_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"Failed writing activity log: {e}")


def log_activity(status: str, message: str, source: str = "system", hotel: str = None,
                 current_price: float = None, paid_price: float = None, savings: float = None):
    """Create and persist a structured activity log entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "source": source,
        "message": message,
        "hotel": hotel,
        "current_price": current_price,
        "paid_price": paid_price,
        "savings": savings
    }
    write_activity_log(entry)
    logger.info(f"[ACTIVITY:{status}] {message}")


def read_recent_activity(limit: int = 100):
    """Read recent activity entries from file."""
    if not ACTIVITY_LOG_FILE.exists():
        return []

    entries = []
    try:
        with open(ACTIVITY_LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Failed reading activity log: {e}")
        return []

    return entries[-limit:]


def send_telegram_alert(message: str):
    """Send alert to Telegram bot if configured."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": message
        }, timeout=15)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def send_confirmation_email(subject: str, body: str):
    """Send confirmation email if SMTP is configured."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not all([smtp_host, smtp_user, smtp_password, email_from, email_to]):
        logger.warning("Email not configured (missing SMTP/EMAIL environment variables)")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_from
        msg["To"] = email_to
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return True
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


def execute_auto_refund_sequence(website: str, hotel_name: str, dates: str,
                                 booking_id: str, current_price: float, savings: float):
    """Execute cancel and rebook sequence using saved credentials."""
    creds = credentials_manager.get_credentials_for_agent(website)
    if not creds:
        return False, f"No saved credentials for {website}"

    username = creds.get('username')
    password = creds.get('password')
    two_fa_code = creds.get('two_fa_code')

    if not username:
        return False, "Missing username in saved credentials"

    if not login_to_booking_site(website, username, password, two_fa_code):
        return False, "Login failed"

    if booking_id:
        if not cancel_booking(website, username, password, booking_id, two_fa_code):
            return False, "Cancellation failed"

    if not rebook_with_new_price(website, username, password, hotel_name, dates, current_price, two_fa_code):
        return False, "Rebooking failed"

    send_telegram_alert(f"✅ Success! Your booking has been updated. You saved ${savings:.2f}! Check your email for the new confirmation.")
    send_confirmation_email(
        subject="RefundFish: Booking Updated Successfully",
        body=f"RefundFish completed your booking update successfully.\n\nHotel: {hotel_name}\nDates: {dates}\nSavings: ${savings:.2f}\n\nCheck your email for the new booking confirmation."
    )
    return True, f"Auto-refund complete. Saved ${savings:.2f}"


def run_price_check(hotel_name: str, dates: str, paid_price: float, booking_id: str = "",
                    source: str = "manual", auto_execute: bool = False):
    """Execute one full price-check cycle and optionally auto-execute cancel/rebook."""
    settings = load_settings()
    website = settings.get('selected_website', 'booking.com')

    logger.info(f"Searching: {hotel_name} for {dates} ({source})")
    current_price = get_current_price(hotel_name, dates)

    if current_price is None:
        log_activity(
            status="error",
            source=source,
            hotel=hotel_name,
            paid_price=paid_price,
            message="Price check failed (TinyFish timeout or API issue)"
        )
        return None, {
            "error": "Could not fetch price - TinyFish timeout or API issue",
            "status": "failed",
            "hotel": hotel_name,
            "dates": dates
        }

    should_rebook, savings = evaluate_refund_opportunity(current_price, paid_price)
    analysis = get_detailed_analysis(current_price, paid_price)
    meets_threshold = savings >= settings['min_savings_threshold']
    lower_price_found = current_price < paid_price
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
        "source": source,
        "timestamp": datetime.now().isoformat()
    }

    log_activity(
        status="success",
        source=source,
        hotel=hotel_name,
        current_price=current_price,
        paid_price=paid_price,
        savings=savings,
        message=f"Price checked. Current: ${current_price:.2f}, Paid: ${paid_price:.2f}, Savings: ${savings:.2f}"
    )

    # For scheduler checks, execute immediately on lower price.
    should_auto_execute = auto_execute and lower_price_found
    if should_auto_execute:
        send_telegram_alert("🔍 RefundFish found a lower price! Attempting to re-book...")
        result["auto_refund_status"] = "processing"
        success, message = execute_auto_refund_sequence(
            website=website,
            hotel_name=hotel_name,
            dates=dates,
            booking_id=booking_id,
            current_price=current_price,
            savings=savings
        )

        if success:
            result["auto_refund_status"] = "success"
            result["message"] = message
            log_activity(
                status="success",
                source=source,
                hotel=hotel_name,
                current_price=current_price,
                paid_price=paid_price,
                savings=savings,
                message=f"Auto-refund completed successfully. {message}"
            )
        else:
            result["auto_refund_status"] = "error"
            result["message"] = message
            log_activity(
                status="error",
                source=source,
                hotel=hotel_name,
                current_price=current_price,
                paid_price=paid_price,
                savings=savings,
                message=f"Auto-refund failed: {message}"
            )

    return result, None


def monitoring_loop():
    """Background monitoring worker (safe, resilient loop)."""
    log_activity("info", "Background monitoring started", source="scheduler")

    while not MONITOR_STOP_EVENT.is_set() and MONITORING_STATE["enabled"]:
        target = MONITORING_STATE.get("target")
        try:
            if target:
                MONITORING_STATE["last_run"] = datetime.now().isoformat()
                run_price_check(
                    hotel_name=target["hotel_name"],
                    dates=target["dates"],
                    paid_price=float(target["paid_price"]),
                    booking_id=target.get("booking_id", ""),
                    source="scheduler",
                    auto_execute=True
                )
        except Exception as e:
            logger.error(f"Scheduler cycle failed: {e}", exc_info=True)
            log_activity("error", f"Scheduler cycle failed: {e}", source="scheduler")

        MONITORING_STATE["next_run"] = (datetime.now() + timedelta(seconds=MONITOR_INTERVAL_SECONDS)).isoformat()

        for _ in range(MONITOR_INTERVAL_SECONDS):
            if MONITOR_STOP_EVENT.wait(1):
                break
            if not MONITORING_STATE["enabled"]:
                break

    log_activity("info", "Background monitoring stopped", source="scheduler")

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
        result, error = run_price_check(
            hotel_name=hotel_name,
            dates=dates,
            paid_price=paid_price,
            booking_id=booking_id,
            source="manual",
            auto_execute=settings.get('auto_refund', False)
        )

        if error:
            return jsonify(error), 500

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


@app.route('/api/activity-log', methods=['GET'])
def get_activity_log():
    """Return recent scheduler/manual activity entries."""
    limit = int(request.args.get('limit', 100))
    entries = read_recent_activity(limit=limit)
    return jsonify(entries)


@app.route('/api/monitoring/status', methods=['GET'])
def monitoring_status():
    """Get current monitoring status."""
    return jsonify({
        "enabled": MONITORING_STATE["enabled"],
        "target": MONITORING_STATE["target"],
        "last_run": MONITORING_STATE["last_run"],
        "next_run": MONITORING_STATE["next_run"]
    })


@app.route('/api/monitoring/start', methods=['POST'])
def monitoring_start():
    """Start background monitoring every 60 minutes."""
    data = request.json or {}
    hotel_name = data.get('hotel_name')
    dates = data.get('dates')
    paid_price = float(data.get('paid_price', 0))
    booking_id = data.get('booking_id', '')

    if not all([hotel_name, dates, paid_price]):
        return jsonify({"error": "Missing required fields for monitoring (hotel_name, dates, paid_price)"}), 400

    MONITORING_STATE["target"] = {
        "hotel_name": hotel_name,
        "dates": dates,
        "paid_price": paid_price,
        "booking_id": booking_id
    }

    if MONITORING_STATE["enabled"]:
        return jsonify({
            "status": "already_running",
            "message": "Monitoring already enabled",
            "target": MONITORING_STATE["target"]
        })

    MONITORING_STATE["enabled"] = True
    MONITOR_STOP_EVENT.clear()

    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    MONITORING_STATE["thread"] = monitor_thread
    monitor_thread.start()

    log_activity("info", f"Monitoring enabled for {hotel_name} every 60 minutes", source="scheduler", hotel=hotel_name)

    return jsonify({
        "status": "started",
        "message": "Monitoring started (60-minute interval)",
        "target": MONITORING_STATE["target"]
    })


@app.route('/api/monitoring/stop', methods=['POST'])
def monitoring_stop():
    """Stop background monitoring safely."""
    if not MONITORING_STATE["enabled"]:
        return jsonify({"status": "already_stopped", "message": "Monitoring already disabled"})

    MONITORING_STATE["enabled"] = False
    MONITORING_STATE["next_run"] = None
    MONITOR_STOP_EVENT.set()

    thread = MONITORING_STATE.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=3)

    log_activity("info", "Monitoring disabled", source="scheduler")

    return jsonify({"status": "stopped", "message": "Monitoring stopped"})

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
