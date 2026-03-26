"""
agents/live_monitor_agent.py
RefundFish - Live Monitor Agent (Session Cookie Mode)
Uses TinyFish to open a booking URL and extract live price from current session.
"""

import re
import time
from typing import Dict, Optional

import requests

from config.settings import TINYFISH_API_KEY
from config.logger import setup_logger

logger = setup_logger("live_monitor_agent")


class LiveMonitorAgent:
    """Live monitor that scrapes current price using existing browser session cookies."""

    def __init__(self, min_cooldown_seconds: int = 180):
        self.min_cooldown_seconds = max(min_cooldown_seconds, 120)
        self.last_run_ts = 0.0

    @staticmethod
    def _extract_price(text: str) -> Optional[float]:
        if not isinstance(text, str):
            return None

        numbers = re.findall(r"\$?\s?(\d+(?:,\d+)?(?:\.\d+)?)", text)
        if not numbers:
            return None

        try:
            return float(numbers[0].replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_labeled_value(text: str, label: str) -> Optional[str]:
        if not isinstance(text, str):
            return None
        pattern = rf"{label}\s*:\s*(.+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip()
        if not value:
            return None
        value = re.split(r"\n|\r", value)[0].strip()
        if value.upper() in {"N/A", "NA", "UNKNOWN", "NONE", "NOT FOUND"}:
            return None
        return value

    @staticmethod
    def _extract_float_from_text(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", value)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_int_from_text(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        match = re.search(r"(\d[\d,]*)", value)
        if not match:
            return None
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None

    def _tinyfish_call(self, booking_url: str, hotel_name: str = "", dates: str = "") -> Optional[str]:
        url = "https://agent.tinyfish.ai/v1/automation/run-sse"
        headers = {
            "X-API-Key": TINYFISH_API_KEY,
            "Content-Type": "application/json",
        }

        goal = f"""
        Use the existing browser session cookies (already authenticated user session).
        Navigate to this booking page URL: {booking_url}
        Hotel context: {hotel_name}
        Date context: {dates}
        Do NOT logout or open unrelated pages.
        Extract these exact fields from the page:
        1) Hotel Name (example selector: h3.hp__hotel-name)
        2) Check-in and Check-out Dates
        3) Room Type (if available)
        4) Current Live Total Price
        5) Star Rating
        6) Vote Count / Number of reviews

        Return only these lines in this exact structure:
        HOTEL_NAME: <value>
        DATES: <value>
        ROOM_TYPE: <value or N/A>
        STAR_RATING: <numeric like 4.2 or N/A>
        VOTE_COUNT: <integer like 128 or N/A>
        PRICE: <numeric value like $123.45>
        """

        payload = {
            "url": booking_url,
            "goal": goal,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            logger.error(f"Live monitor TinyFish call failed: {exc}")
            return None

    def fetch_live_price(self, booking_url: str, hotel_name: str = "", dates: str = "") -> Dict:
        now_ts = time.time()
        elapsed = now_ts - self.last_run_ts
        if elapsed < self.min_cooldown_seconds:
            wait_seconds = int(self.min_cooldown_seconds - elapsed)
            return {
                "status": "cooldown",
                "message": f"Cooldown active. Next allowed check in {wait_seconds}s",
                "price": None,
                "raw": "",
            }

        self.last_run_ts = now_ts

        response_text = self._tinyfish_call(booking_url, hotel_name, dates)
        if response_text is None:
            return {
                "status": "error",
                "message": "TinyFish did not return a valid response",
                "price": None,
                "raw": "",
            }

        price = self._extract_price(response_text)
        extracted_hotel = self._extract_labeled_value(response_text, "HOTEL_NAME") or hotel_name
        extracted_dates = self._extract_labeled_value(response_text, "DATES") or dates
        extracted_room_type = self._extract_labeled_value(response_text, "ROOM_TYPE")
        extracted_star_rating = self._extract_float_from_text(self._extract_labeled_value(response_text, "STAR_RATING"))
        extracted_vote_count = self._extract_int_from_text(self._extract_labeled_value(response_text, "VOTE_COUNT"))

        if price is None:
            return {
                "status": "error",
                "message": "Could not extract live price from page",
                "price": None,
                "hotel_name": extracted_hotel,
                "dates": extracted_dates,
                "room_type": extracted_room_type,
                "star_rating": extracted_star_rating,
                "vote_count": extracted_vote_count,
                "raw": response_text[:400],
            }

        return {
            "status": "success",
            "message": "Live price extracted successfully",
            "price": float(price),
            "hotel_name": extracted_hotel,
            "dates": extracted_dates,
            "room_type": extracted_room_type,
            "star_rating": extracted_star_rating,
            "vote_count": extracted_vote_count,
            "raw": response_text[:400],
        }
