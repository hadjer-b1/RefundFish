"""
RefundFish Web Application
Flask backend serving HTML UI with real-time TinyFish integration
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import time
import re
from pathlib import Path
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import requests
from agents.browser_agent import get_current_price, login_to_booking_site, fetch_reservations, cancel_booking, rebook_with_new_price, manage_favorites
from agents.live_monitor_agent import LiveMonitorAgent
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
LIVE_MONITOR_INTERVAL_SECONDS = max(int(os.getenv("LIVE_MONITOR_INTERVAL_SECONDS", "300")), 180)
MONITOR_STOP_EVENT = threading.Event()
MONITORING_STATE = {
    "enabled": False,
    "target": None,
    "last_run": None,
    "next_run": None,
    "thread": None
}
LIVE_MONITOR_STOP_EVENT = threading.Event()
LIVE_MONITOR_STATE = {
    "enabled": False,
    "connected_via_session_cookies": True,
    "target": None,
    "last_run": None,
    "next_run": None,
    "last_live_price": None,
    "last_star_rating": None,
    "last_vote_count": None,
    "good_price_recommended": False,
    "last_drop": None,
    "price_drop_detected": False,
    "thread": None,
}
live_monitor_agent = LiveMonitorAgent(min_cooldown_seconds=LIVE_MONITOR_INTERVAL_SECONDS)


def write_activity_log(entry: dict):
    """Persist activity entry to file and logger."""
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = entry.get("log_line") or json.dumps(entry, ensure_ascii=False)
        with open(ACTIVITY_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{line}\n")
    except Exception as e:
        logger.error(f"Failed writing activity log: {e}")


def _parse_log_line(raw_line: str):
    """Parse text log line back into dict entries for API/UI compatibility."""
    line = raw_line.strip()
    if not line:
        return None

    if line.startswith("🔴 ALERT:"):
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "warning",
            "source": "live-monitor",
            "message": line,
            "hotel": None,
            "current_price": None,
            "paid_price": None,
            "savings": None,
            "dates": None,
            "room_type": None,
            "log_line": line,
        }

    match = re.match(
        r"^\[(?P<timestamp>[^\]]+)\]\s\|\sHotel:\s(?P<hotel>.*?)\s\|\sPrice:\s(?P<price>.*?)\s\|\sStatus:\s(?P<status>.+)$",
        line,
    )
    if not match:
        found_match = re.match(
            r"^\[(?P<timestamp>[^\]]+)\]\s\|\sFound:\s(?P<hotel>.*?)\s\|\sRating:\s(?P<rating>.*?)\s\|\sPrice:\s(?P<price>.*?)\s\|\sStatus:\s(?P<status>.+)$",
            line,
        )
        if not found_match:
            return None

        found_price_text = (found_match.group("price") or "").replace("$", "").replace(",", "").strip()
        found_price_match = re.search(r"(\d+(?:\.\d+)?)", found_price_text)
        found_price_value = float(found_price_match.group(1)) if found_price_match else None

        return {
            "timestamp": found_match.group("timestamp"),
            "status": "success",
            "source": "live-monitor",
            "message": line,
            "hotel": found_match.group("hotel"),
            "current_price": found_price_value,
            "paid_price": None,
            "savings": None,
            "dates": None,
            "room_type": None,
            "log_line": line,
            "rating": found_match.group("rating"),
        }

    price_text = (match.group("price") or "").replace("$", "").replace(",", "").strip()
    price_value = None
    try:
        if price_text:
            price_value = float(price_text)
    except ValueError:
        price_value = None

    status_text = (match.group("status") or "").strip()
    status_value = "warning" if "Dropped" in status_text else "success"

    return {
        "timestamp": match.group("timestamp"),
        "status": status_value,
        "source": "live-monitor",
        "message": line,
        "hotel": match.group("hotel"),
        "current_price": price_value,
        "paid_price": None,
        "savings": None,
        "dates": None,
        "room_type": None,
        "log_line": line,
    }


def log_activity(status: str, message: str, source: str = "system", hotel: str = None,
                 current_price: float = None, paid_price: float = None, savings: float = None,
                 dates: str = None, room_type: str = None):
    """Create and persist a structured activity log entry."""
    timestamp = datetime.now().isoformat()
    if message.startswith("🔴 ALERT:") or (message.startswith("[") and "| Found:" in message):
        log_line = message
    elif hotel and current_price is not None:
        status_text = "Dropped!" if (savings is not None and savings > 0) else "Stayed Same"
        log_line = f"[{timestamp}] | Hotel: {hotel} | Price: ${current_price:.2f} | Status: {status_text}"
    else:
        log_line = f"[{timestamp}] | Hotel: {hotel or 'N/A'} | Price: N/A | Status: {message}"

    entry = {
        "timestamp": timestamp,
        "status": status,
        "source": source,
        "message": log_line,
        "hotel": hotel,
        "current_price": current_price,
        "paid_price": paid_price,
        "savings": savings,
        "dates": dates,
        "room_type": room_type,
        "log_line": log_line,
    }
    write_activity_log(entry)
    logger.info(f"[ACTIVITY:{status}] {log_line}")


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
                    parsed = _parse_log_line(line)
                    if parsed:
                        entries.append(parsed)
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


def _get_email_config():
    """Resolve SMTP/email config from new keys with backward-compatible fallbacks."""
    smtp_server = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    email_user = os.getenv("EMAIL_USER") or os.getenv("SMTP_USER")
    email_pass = os.getenv("EMAIL_PASS") or os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM") or email_user
    email_from_name = os.getenv("EMAIL_FROM_NAME", "RefundFish Support")
    return smtp_server, smtp_port, email_user, email_pass, email_from, email_from_name


def _build_success_email_html(booking_details: dict):
    """Create professional success HTML template with inline CSS."""
    hotel_name = booking_details.get("hotel_name", "N/A")
    dates = booking_details.get("dates", "N/A")
    old_price = booking_details.get("old_price", 0)
    new_price = booking_details.get("new_price", 0)
    savings = booking_details.get("savings", 0)
    new_confirmation_number = booking_details.get("new_confirmation_number") or "Not available"

    return f"""
        <html>
            <body style="font-family: Arial, sans-serif; background: #f6f8fb; color: #1f2937; margin: 0; padding: 20px;">
                <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
                    <div style="background: #1e3a8a; color: #ffffff; padding: 18px 20px; font-size: 18px; font-weight: 700;">
                        RefundFish Booking Update
                    </div>
                    <div style="padding: 20px; line-height: 1.5;">
                        <p style="margin-top: 0;"><strong>Hello!</strong> Great news, your RefundFish agent has successfully optimized your booking.</p>

                        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                            <tr>
                                <th style="text-align: left; border: 1px solid #e5e7eb; background: #f9fafb; padding: 10px;">Metric</th>
                                <th style="text-align: left; border: 1px solid #e5e7eb; background: #f9fafb; padding: 10px;">Value</th>
                            </tr>
                            <tr>
                                <td style="border: 1px solid #e5e7eb; padding: 10px;">Old Price</td>
                                <td style="border: 1px solid #e5e7eb; padding: 10px;">${old_price:.2f}</td>
                            </tr>
                            <tr>
                                <td style="border: 1px solid #e5e7eb; padding: 10px;">New Price</td>
                                <td style="border: 1px solid #e5e7eb; padding: 10px;">${new_price:.2f}</td>
                            </tr>
                            <tr>
                                <td style="border: 1px solid #e5e7eb; padding: 10px;"><strong>Total Savings</strong></td>
                                <td style="border: 1px solid #e5e7eb; padding: 10px; color: #059669;"><strong>${savings:.2f}</strong></td>
                            </tr>
                        </table>

                        <p style="margin: 8px 0;"><strong>Action Taken:</strong> Your previous reservation has been cancelled, and a new one has been secured at the lower rate.</p>

                        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                            <tr><td style="padding: 6px 0;"><strong>Hotel:</strong> {hotel_name}</td></tr>
                            <tr><td style="padding: 6px 0;"><strong>Dates:</strong> {dates}</td></tr>
                            <tr><td style="padding: 6px 0;"><strong>New Confirmation Number:</strong> {new_confirmation_number}</td></tr>
                        </table>

                        <p style="margin-bottom: 0; color: #6b7280; font-size: 13px; border-top: 1px solid #e5e7eb; padding-top: 14px;">
                            Powered by RefundFish AI - Monitoring your savings 24/7.
                        </p>
                    </div>
                </div>
            </body>
        </html>
    """


def _build_alert_email_html(booking_details: dict):
    """Create failure alert HTML template."""
    hotel_name = booking_details.get("hotel_name", "N/A")
    dates = booking_details.get("dates", "N/A")
    old_price = booking_details.get("old_price", 0)
    new_price = booking_details.get("new_price", 0)
    savings = booking_details.get("savings", 0)
    failure_reason = booking_details.get("failure_reason", "Unknown reason")

    return f"""
        <html>
            <body style="font-family: Arial, sans-serif; background: #f6f8fb; color: #1f2937; margin: 0; padding: 20px;">
                <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
                    <div style="background: #b91c1c; color: #ffffff; padding: 18px 20px; font-size: 18px; font-weight: 700;">
                        RefundFish System Alert
                    </div>
                    <div style="padding: 20px; line-height: 1.5;">
                        <p style="margin-top: 0;"><strong>Action Required:</strong> A price drop was found, but manual intervention is needed to complete the re-booking.</p>
                        <p><strong>Reason:</strong> {failure_reason}</p>
                        <p><strong>Hotel:</strong> {hotel_name}<br/><strong>Dates:</strong> {dates}</p>
                        <p><strong>Old Price:</strong> ${old_price:.2f}<br/><strong>Detected Price:</strong> ${new_price:.2f}<br/><strong>Potential Savings:</strong> ${savings:.2f}</p>
                        <p style="margin-bottom: 0; color: #6b7280; font-size: 13px; border-top: 1px solid #e5e7eb; padding-top: 14px;">
                            Powered by RefundFish AI - Monitoring your savings 24/7.
                        </p>
                    </div>
                </div>
            </body>
        </html>
    """


def _send_email_thread(user_email: str, booking_details: dict, is_alert: bool = False):
    """Background worker for sending email notifications."""
    smtp_server, smtp_port, email_user, email_pass, email_from, email_from_name = _get_email_config()
    recipient = user_email or booking_details.get("user_email") or os.getenv("EMAIL_TO")

    if not all([smtp_server, email_user, email_pass, email_from, recipient]):
        logger.warning("Email not configured (SMTP_SERVER/EMAIL_USER/EMAIL_PASS/EMAIL_FROM/recipient)")
        log_activity("warning", "Email not sent: missing SMTP config or recipient", source="email", hotel=booking_details.get("hotel_name"))
        return

    savings = float(booking_details.get("savings", 0) or 0)
    if is_alert:
        subject = "RefundFish Alert: Action required for booking re-book"
        html_body = _build_alert_email_html(booking_details)
        plain_body = "Action Required: A price drop was found, but manual intervention is needed to complete the re-booking."
    else:
        subject = f"🐟 RefundFish Success: We just saved you ${savings:.2f} on your booking!"
        html_body = _build_success_email_html(booking_details)
        plain_body = f"RefundFish optimized your booking and saved ${savings:.2f}."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((email_from_name, email_from))
        msg["To"] = recipient
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_from, [recipient], msg.as_string())

        log_activity("success", f"Email Sent to {recipient}", source="email", hotel=booking_details.get("hotel_name"), savings=savings)
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        log_activity("error", f"Email send failed: {e}", source="email", hotel=booking_details.get("hotel_name"), savings=savings)


def send_confirmation_email(user_email: str, booking_details: dict, is_alert: bool = False):
    """Queue email in background thread so UI/scheduler are never blocked."""
    thread = threading.Thread(
        target=_send_email_thread,
        args=(user_email, booking_details, is_alert),
        daemon=True
    )
    thread.start()
    return True


def send_live_price_drop_email(user_email: str, booking_details: dict):
    """Send a price-drop detection email in background thread."""
    details = dict(booking_details)
    details["failure_reason"] = "Price drop detected. Click Execute Auto-Rebook in the dashboard to apply the booking update."
    send_confirmation_email(user_email=user_email, booking_details=details, is_alert=True)


def send_wishlist_saved_email(user_email: str, hotel_name: str, dates: str):
    """Send Smart Wishlist confirmation message."""
    message = f"🔥 Price Drop Detected! RefundFish has saved {hotel_name} to your Booking.com Favorites. Go grab it before it's gone!"

    def _worker():
        smtp_server, smtp_port, email_user, email_pass, email_from, email_from_name = _get_email_config()
        recipient = user_email or os.getenv("EMAIL_TO")
        if not all([smtp_server, email_user, email_pass, email_from, recipient]):
            logger.warning("Wishlist email not configured (SMTP_SERVER/EMAIL_USER/EMAIL_PASS/EMAIL_FROM/recipient)")
            return

        html_body = f"""
        <html>
            <body style=\"font-family: Arial, sans-serif;\">
                <h2>RefundFish Smart Wishlist Hunter</h2>
                <p>{message}</p>
                <p><strong>Hotel:</strong> {hotel_name}<br/><strong>Dates:</strong> {dates}</p>
            </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "RefundFish Smart Wishlist Alert"
        msg["From"] = formataddr((email_from_name, email_from))
        msg["To"] = recipient
        msg.attach(MIMEText(f"{message}\nHotel: {hotel_name}\nDates: {dates}", "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(email_user, email_pass)
                server.sendmail(email_from, [recipient], msg.as_string())
            log_activity("success", f"Email Sent to {recipient}", source="email", hotel=hotel_name, dates=dates)
        except Exception as exc:
            logger.error(f"Failed to send Smart Wishlist email: {exc}")

    threading.Thread(target=_worker, daemon=True).start()


def execute_auto_refund_sequence(website: str, hotel_name: str, dates: str,
                                 booking_id: str, current_price: float, savings: float,
                                 hotel_url: str = "", target_price: float = 0,
                                 preview_only: bool = False):
    """Execute smart wishlist save/unsave sequence using saved credentials."""
    creds = credentials_manager.get_credentials_for_agent(website)
    if not creds:
        return False, f"No saved credentials for {website}"

    username = creds.get('username')
    email = creds.get('email')
    password = creds.get('password')
    two_fa_code = creds.get('two_fa_code')
    recipient_email = email or username

    if not username:
        return False, "Missing username in saved credentials", recipient_email, None

    if not login_to_booking_site(website, username, password, two_fa_code):
        return False, "Login failed", recipient_email, None

    if not hotel_url:
        target = LIVE_MONITOR_STATE.get("target") or {}
        hotel_url = target.get("booking_url", "")

    wishlist_result = manage_favorites(
        website=website,
        username=username,
        password=password,
        hotel_url=hotel_url,
        target_price=target_price if target_price > 0 else current_price,
        two_fa_code=two_fa_code,
        hotel_name_query=hotel_name,
        dates=dates,
        currency="USD",
        preview_only=preview_only,
        top_n=3,
    )

    if not wishlist_result.get("success"):
        return False, wishlist_result.get("message", "Smart Wishlist Hunter failed"), recipient_email, None

    resolved_hotel_name = wishlist_result.get("hotel_name") or hotel_name
    action = wishlist_result.get("action")

    if wishlist_result.get("preview_required"):
        return True, wishlist_result.get("message", "Preview generated"), recipient_email, {
            "preview_required": True,
            "extracted_deals": wishlist_result.get("extracted_deals", []),
        }

    for added in wishlist_result.get("added_hotels", []):
        added_name = added.get("hotel_name", "Unknown Hotel")
        added_rating = float(added.get("rating") or 0)
        added_currency = added.get("currency", "USD")
        added_price = float(added.get("final_price") or 0)
        found_line = f"[{datetime.now().isoformat()}] | Found: {added_name} | Rating: {added_rating:.1f} | Price: {added_currency} {added_price:.2f} | Status: Added to Favs ✅"
        log_activity(
            status="success",
            message=found_line,
            source="live-monitor",
            hotel=added_name,
            current_price=added_price,
            dates=dates,
        )

    if action == "saved":
        wishlist_message = f"🔥 Price Drop Detected! RefundFish has saved {resolved_hotel_name} to your Booking.com Favorites. Go grab it before it's gone!"
        send_telegram_alert(wishlist_message)
        send_wishlist_saved_email(recipient_email, resolved_hotel_name, dates)
        return True, wishlist_result.get("message", "Added to favorites"), recipient_email, None

    return True, wishlist_result.get("message", "No favorite change"), recipient_email, None


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
        success, message, recipient_email, new_confirmation_number = execute_auto_refund_sequence(
            website=website,
            hotel_name=hotel_name,
            dates=dates,
            booking_id=booking_id,
            current_price=current_price,
            savings=savings,
            target_price=paid_price,
        )

        if success:
            result["auto_refund_status"] = "success"
            result["message"] = message
            result["new_confirmation_number"] = new_confirmation_number
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
            send_confirmation_email(
                user_email=recipient_email,
                booking_details={
                    "hotel_name": hotel_name,
                    "dates": dates,
                    "old_price": paid_price,
                    "new_price": current_price,
                    "savings": savings,
                    "failure_reason": message,
                    "user_email": recipient_email
                },
                is_alert=True
            )
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


def run_live_monitor_check(source: str = "live-monitor"):
    """Execute one live monitor cycle using either booking URL or hotel/date query."""
    target = LIVE_MONITOR_STATE.get("target")
    if not target:
        return None, "Live monitor target is not configured"

    booking_url = target.get("booking_url")
    hotel_name = target.get("hotel_name", "")
    dates = target.get("dates", "")
    target_price = float(target.get("target_price", 0) or 0)
    paid_price = float(target.get("paid_price", 0) or 0)
    booking_id = target.get("booking_id", "")
    website = target.get("website") or load_settings().get("selected_website", "booking.com")

    if target_price <= 0:
        return None, "Missing target_price"

    if not booking_url:
        if not hotel_name or not dates:
            return None, "Missing hotel_name/dates when booking_url is not provided"

        LIVE_MONITOR_STATE["last_run"] = datetime.now().isoformat()
        LIVE_MONITOR_STATE["next_run"] = (datetime.now() + timedelta(seconds=LIVE_MONITOR_INTERVAL_SECONDS)).isoformat()

        success, message, recipient_email, _ = execute_auto_refund_sequence(
            website=website,
            hotel_name=hotel_name,
            dates=dates,
            booking_id=booking_id,
            current_price=target_price,
            savings=0,
            hotel_url="",
            target_price=target_price,
            preview_only=False,
        )

        auto_favorited = bool(success and ("added" in message.lower() or "saved" in message.lower()))
        LIVE_MONITOR_STATE["price_drop_detected"] = auto_favorited
        LIVE_MONITOR_STATE["last_live_price"] = target_price if auto_favorited else None
        LIVE_MONITOR_STATE["last_star_rating"] = None
        LIVE_MONITOR_STATE["last_vote_count"] = None
        LIVE_MONITOR_STATE["good_price_recommended"] = auto_favorited

        if auto_favorited:
            LIVE_MONITOR_STATE["last_drop"] = {
                "hotel_name": hotel_name,
                "dates": dates,
                "room_type": None,
                "website": website,
                "booking_id": booking_id,
                "booking_url": "",
                "target_price": target_price,
                "paid_price": paid_price if paid_price > 0 else target_price,
                "current_live_price": target_price,
                "star_rating": None,
                "vote_count": None,
                "good_price_recommended": True,
                "savings": 0,
                "timestamp": datetime.now().isoformat(),
            }

        if success:
            log_activity(
                status="success",
                source=source,
                hotel=hotel_name,
                current_price=target_price,
                paid_price=target_price,
                savings=0,
                message=f"Auto wishlist check complete: {message}",
                dates=dates,
                room_type=None,
            )
            return {
                "status": "success",
                "message": message,
                "current_live_price": target_price if auto_favorited else None,
                "star_rating": None,
                "vote_count": None,
                "good_price_recommended": auto_favorited,
                "target_price": target_price,
                "price_drop_detected": auto_favorited,
                "last_drop": LIVE_MONITOR_STATE.get("last_drop"),
            }, None

        log_activity(
            status="error",
            source=source,
            hotel=hotel_name,
            current_price=None,
            paid_price=target_price,
            savings=0,
            message=f"Auto wishlist check failed: {message}",
            dates=dates,
            room_type=None,
        )
        return {
            "status": "error",
            "message": message,
            "star_rating": None,
            "vote_count": None,
            "good_price_recommended": False,
            "target_price": target_price,
            "current_live_price": None,
            "price_drop_detected": False,
        }, None

    check_result = live_monitor_agent.fetch_live_price(
        booking_url=booking_url,
        hotel_name=hotel_name,
        dates=dates
    )

    extracted_hotel = check_result.get("hotel_name") or hotel_name
    extracted_dates = check_result.get("dates") or dates
    extracted_room_type = check_result.get("room_type")
    extracted_star_rating = check_result.get("star_rating")
    extracted_vote_count = check_result.get("vote_count")

    if check_result["status"] == "cooldown":
        log_activity("info", check_result["message"], source=source, hotel=extracted_hotel, dates=extracted_dates, room_type=extracted_room_type)
        return {
            "status": "cooldown",
            "message": check_result["message"],
            "current_live_price": LIVE_MONITOR_STATE.get("last_live_price"),
            "star_rating": LIVE_MONITOR_STATE.get("last_star_rating"),
            "vote_count": LIVE_MONITOR_STATE.get("last_vote_count"),
            "good_price_recommended": LIVE_MONITOR_STATE.get("good_price_recommended", False),
            "target_price": target_price,
            "price_drop_detected": LIVE_MONITOR_STATE.get("price_drop_detected", False),
        }, None

    if check_result["status"] != "success":
        log_activity("error", f"Live monitor check failed: {check_result['message']}", source=source, hotel=extracted_hotel, dates=extracted_dates, room_type=extracted_room_type)
        return {
            "status": "error",
            "message": check_result["message"],
            "star_rating": extracted_star_rating,
            "vote_count": extracted_vote_count,
            "good_price_recommended": False,
            "target_price": target_price,
            "current_live_price": None,
            "price_drop_detected": False,
        }, None

    current_live_price = float(check_result["price"])
    good_price_recommended = bool(
        extracted_vote_count is not None and extracted_vote_count > 20 and
        extracted_star_rating is not None and extracted_star_rating > 3.5
    )

    LIVE_MONITOR_STATE["last_live_price"] = current_live_price
    LIVE_MONITOR_STATE["last_star_rating"] = extracted_star_rating
    LIVE_MONITOR_STATE["last_vote_count"] = extracted_vote_count
    LIVE_MONITOR_STATE["good_price_recommended"] = good_price_recommended
    LIVE_MONITOR_STATE["last_run"] = datetime.now().isoformat()
    LIVE_MONITOR_STATE["next_run"] = (datetime.now() + timedelta(seconds=LIVE_MONITOR_INTERVAL_SECONDS)).isoformat()

    drop_detected = current_live_price < target_price
    LIVE_MONITOR_STATE["price_drop_detected"] = drop_detected

    log_activity(
        status="success",
        source=source,
        hotel=extracted_hotel,
        current_price=current_live_price,
        paid_price=target_price,
        savings=(target_price - current_live_price),
        message=f"Live check complete. Target: ${target_price:.2f}, Live: ${current_live_price:.2f}",
        dates=extracted_dates,
        room_type=extracted_room_type,
    )

    if drop_detected:
        drop_savings = target_price - current_live_price
        LIVE_MONITOR_STATE["last_drop"] = {
            "hotel_name": extracted_hotel,
            "dates": extracted_dates,
            "room_type": extracted_room_type,
            "website": website,
            "booking_id": booking_id,
            "booking_url": booking_url,
            "target_price": target_price,
            "paid_price": paid_price if paid_price > 0 else target_price,
            "current_live_price": current_live_price,
            "star_rating": extracted_star_rating,
            "vote_count": extracted_vote_count,
            "good_price_recommended": good_price_recommended,
            "savings": drop_savings,
            "timestamp": datetime.now().isoformat(),
        }

        alert_message = (
            f"🔍 RefundFish found a lower price! Smart Wishlist Hunter is ready.\n"
            f"Hotel: {extracted_hotel}\n"
            f"Dates: {extracted_dates}\n"
            f"Target: ${target_price:.2f}\n"
            f"Live: ${current_live_price:.2f}\n"
            f"Potential savings: ${drop_savings:.2f}"
        )
        send_telegram_alert(alert_message)

        creds = credentials_manager.get_credentials_for_agent(website)
        recipient_email = None
        if creds:
            recipient_email = creds.get("email") or creds.get("username")

        send_live_price_drop_email(
            user_email=recipient_email,
            booking_details={
                "hotel_name": extracted_hotel,
                "dates": extracted_dates,
                "old_price": target_price,
                "new_price": current_live_price,
                "savings": drop_savings,
                "room_type": extracted_room_type,
                "user_email": recipient_email,
            },
        )

        log_activity(
            status="warning",
            source=source,
            hotel=extracted_hotel,
            current_price=current_live_price,
            paid_price=target_price,
            savings=drop_savings,
            message=f"🔴 ALERT: Price dropped from ${target_price:.2f} to ${current_live_price:.2f} for {extracted_hotel} ({extracted_dates})",
            dates=extracted_dates,
            room_type=extracted_room_type,
        )

    return {
        "status": "success",
        "message": "Live monitor check completed",
        "current_live_price": current_live_price,
        "star_rating": extracted_star_rating,
        "vote_count": extracted_vote_count,
        "good_price_recommended": good_price_recommended,
        "target_price": target_price,
        "price_drop_detected": drop_detected,
        "last_drop": LIVE_MONITOR_STATE.get("last_drop"),
    }, None


def live_monitor_loop():
    """Background loop for live monitor checks with safe interval."""
    log_activity("info", f"Live Monitor started (interval {LIVE_MONITOR_INTERVAL_SECONDS}s)", source="live-monitor")

    while not LIVE_MONITOR_STOP_EVENT.is_set() and LIVE_MONITOR_STATE["enabled"]:
        try:
            run_live_monitor_check(source="live-monitor")
        except Exception as exc:
            logger.error(f"Live monitor cycle failed: {exc}", exc_info=True)
            log_activity("error", f"Live monitor cycle failed: {exc}", source="live-monitor")

        LIVE_MONITOR_STATE["next_run"] = (datetime.now() + timedelta(seconds=LIVE_MONITOR_INTERVAL_SECONDS)).isoformat()

        for _ in range(LIVE_MONITOR_INTERVAL_SECONDS):
            if LIVE_MONITOR_STOP_EVENT.wait(1):
                break
            if not LIVE_MONITOR_STATE["enabled"]:
                break

    log_activity("info", "Live Monitor stopped", source="live-monitor")

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
    """Get current monitoring status (Hybrid Live Monitor mode)."""
    return jsonify({
        "enabled": LIVE_MONITOR_STATE["enabled"],
        "connected_via_session_cookies": LIVE_MONITOR_STATE["connected_via_session_cookies"],
        "target": LIVE_MONITOR_STATE["target"],
        "last_run": LIVE_MONITOR_STATE["last_run"],
        "next_run": LIVE_MONITOR_STATE["next_run"],
        "current_live_price": LIVE_MONITOR_STATE["last_live_price"],
        "star_rating": LIVE_MONITOR_STATE["last_star_rating"],
        "vote_count": LIVE_MONITOR_STATE["last_vote_count"],
        "good_price_recommended": LIVE_MONITOR_STATE["good_price_recommended"],
        "price_drop_detected": LIVE_MONITOR_STATE["price_drop_detected"],
        "last_drop": LIVE_MONITOR_STATE["last_drop"],
        "interval_seconds": LIVE_MONITOR_INTERVAL_SECONDS,
    })


@app.route('/api/monitoring/start', methods=['POST'])
def monitoring_start():
    """Start Live Monitor using booking URL or hotel/date query."""
    data = request.json or {}
    hotel_name = data.get('hotel_name') or ''
    dates = data.get('dates') or ''
    booking_url = data.get('booking_url') or ''
    target_price = float(data.get('target_price', 0) or 0)
    paid_price = float(data.get('paid_price', 0) or 0)
    booking_id = data.get('booking_id', '')
    website = data.get('website') or load_settings().get('selected_website', 'booking.com')

    if target_price <= 0:
        return jsonify({"error": "Missing required field: target_price"}), 400

    if not booking_url and not all([hotel_name, dates]):
        return jsonify({"error": "Provide booking_url OR hotel_name + dates"}), 400

    LIVE_MONITOR_STATE["target"] = {
        "hotel_name": hotel_name,
        "dates": dates,
        "booking_url": booking_url,
        "target_price": target_price,
        "paid_price": paid_price,
        "booking_id": booking_id,
        "website": website,
    }

    if LIVE_MONITOR_STATE["enabled"]:
        return jsonify({
            "status": "already_running",
            "message": "Live Monitor already enabled",
            "target": LIVE_MONITOR_STATE["target"]
        })

    LIVE_MONITOR_STATE["enabled"] = True
    LIVE_MONITOR_STOP_EVENT.clear()
    LIVE_MONITOR_STATE["price_drop_detected"] = False
    LIVE_MONITOR_STATE["last_drop"] = None
    LIVE_MONITOR_STATE["last_star_rating"] = None
    LIVE_MONITOR_STATE["last_vote_count"] = None
    LIVE_MONITOR_STATE["good_price_recommended"] = False

    monitor_thread = threading.Thread(target=live_monitor_loop, daemon=True)
    LIVE_MONITOR_STATE["thread"] = monitor_thread
    monitor_thread.start()

    log_activity(
        "info",
        f"Live Monitor enabled for {hotel_name or booking_url} (cookies mode, {LIVE_MONITOR_INTERVAL_SECONDS}s interval)",
        source="live-monitor",
        hotel=hotel_name,
    )

    return jsonify({
        "status": "started",
        "message": "Live Monitor started",
        "target": LIVE_MONITOR_STATE["target"]
    })


@app.route('/api/monitoring/stop', methods=['POST'])
def monitoring_stop():
    """Stop live monitor safely."""
    if not LIVE_MONITOR_STATE["enabled"]:
        return jsonify({"status": "already_stopped", "message": "Live Monitor already disabled"})

    LIVE_MONITOR_STATE["enabled"] = False
    LIVE_MONITOR_STATE["next_run"] = None
    LIVE_MONITOR_STOP_EVENT.set()

    thread = LIVE_MONITOR_STATE.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=3)

    log_activity("info", "Live Monitor disabled", source="live-monitor")

    return jsonify({"status": "stopped", "message": "Live Monitor stopped"})


@app.route('/api/live-monitor/run-once', methods=['POST'])
def live_monitor_run_once():
    """Run one live monitor check instantly for demo/testing."""
    data = request.json or {}
    if data:
        # Allow one-shot target override
        try:
            LIVE_MONITOR_STATE["target"] = {
                "hotel_name": data.get('hotel_name', ''),
                "dates": data.get('dates', ''),
                "booking_url": data.get('booking_url', ''),
                "target_price": float(data.get('target_price', 0) or 0),
                "paid_price": float(data.get('paid_price', 0) or 0),
                "booking_id": data.get('booking_id', ''),
                "website": data.get('website') or load_settings().get('selected_website', 'booking.com'),
            }
        except Exception:
            return jsonify({"error": "Invalid request values"}), 400

    result, error = run_live_monitor_check(source="live-monitor-manual")
    if error:
        return jsonify({"status": "error", "error": error}), 400
    return jsonify(result)


@app.route('/api/live-monitor/execute-smart-wishlist', methods=['POST'])
@app.route('/api/live-monitor/execute-auto-rebook', methods=['POST'])
def live_monitor_execute_auto_rebook():
    """Execute Smart Wishlist Hunter action after live drop detection."""
    payload = request.json or {}
    drop_context = LIVE_MONITOR_STATE.get("last_drop") or {}

    # Allow manual override from request if user clicks button with fields
    hotel_name = payload.get('hotel_name') or drop_context.get('hotel_name') or ''
    dates = payload.get('dates') or drop_context.get('dates') or ''
    website = payload.get('website') or drop_context.get('website') or load_settings().get('selected_website', 'booking.com')
    booking_id = payload.get('booking_id') or drop_context.get('booking_id') or ''
    booking_url = payload.get('booking_url') or drop_context.get('booking_url') or ''
    current_live_price = float(payload.get('current_live_price') or drop_context.get('current_live_price') or 0)
    paid_price = float(payload.get('paid_price') or drop_context.get('paid_price') or 0)
    confirm_hearting = bool(payload.get('confirm_hearting', True))

    if not all([hotel_name, dates, website, current_live_price > 0, paid_price > 0]):
        return jsonify({"status": "error", "error": "Missing required live-monitor context for smart wishlist"}), 400

    savings = paid_price - current_live_price
    success, message, recipient_email, new_confirmation_number = execute_auto_refund_sequence(
        website=website,
        hotel_name=hotel_name,
        dates=dates,
        booking_id=booking_id,
        current_price=current_live_price,
        savings=savings,
        hotel_url=booking_url,
        target_price=paid_price,
        preview_only=not confirm_hearting,
    )

    if success and isinstance(new_confirmation_number, dict) and new_confirmation_number.get("preview_required"):
        extracted = new_confirmation_number.get("extracted_deals", [])
        log_activity(
            status="info",
            source="live-monitor",
            hotel=hotel_name,
            current_price=current_live_price,
            paid_price=paid_price,
            savings=savings,
            message=f"Preview generated for Smart Deal Hunter ({len(extracted)} deal(s)).",
        )
        return jsonify({
            "status": "preview",
            "message": message,
            "preview_required": True,
            "extracted_deals": extracted,
            "next_step": "Review extracted_deals, then call this endpoint again with confirm_hearting=true.",
        })

    if success:
        LIVE_MONITOR_STATE["price_drop_detected"] = False
        log_activity(
            status="success",
            source="live-monitor",
            hotel=hotel_name,
            current_price=current_live_price,
            paid_price=paid_price,
            savings=savings,
            message=f"Execute Smart Wishlist Hunter succeeded. {message}",
        )
        return jsonify({
            "status": "success",
            "message": message,
            "recipient_email": recipient_email,
        })

    # Failure path: trigger manual intervention email alert
    send_confirmation_email(
        user_email=recipient_email,
        booking_details={
            "hotel_name": hotel_name,
            "dates": dates,
            "old_price": paid_price,
            "new_price": current_live_price,
            "savings": savings,
            "failure_reason": message,
            "user_email": recipient_email,
        },
        is_alert=True,
    )
    log_activity(
        status="error",
        source="live-monitor",
        hotel=hotel_name,
        current_price=current_live_price,
        paid_price=paid_price,
        savings=savings,
        message=f"Execute Smart Wishlist Hunter failed: {message}",
    )
    return jsonify({"status": "error", "error": message}), 500

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
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    logger.info(f"Starting RefundFish Web UI on http://{host}:{port}")
    app.run(debug=False, host=host, port=port, use_reloader=False)
