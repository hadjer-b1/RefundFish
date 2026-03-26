"""
config/settings.py
RefundFish - Central Configuration
"""

import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ================================
# API KEYS - from environment (safer than hardcoding)
# ================================
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# التحقق من وجود المفاتيح المطلوبة
if not TINYFISH_API_KEY:
    raise ValueError("TINYFISH_API_KEY not found in .env")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env")

# ================================
# PROJECT PATHS - مسارات المشروع
# ================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
TESTS_DIR = BASE_DIR / "tests"

# إنشاء المجلدات إذا لم تكن موجودة
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ================================
# BROWSER AGENT SETTINGS - إعدادات وكيل المتصفح
# ================================
# المنصات المدعومة للبحث
SUPPORTED_PLATFORMS = {
    "google_hotels": "https://www.google.com/travel/hotels",
    "booking": "https://www.booking.com",
    "expedia": "https://www.expedia.com"
}

# المنصات المدعومة لإعادة الحجز
REBOOKING_PLATFORMS = {
    "booking": "https://www.booking.com",
    "expedia": "https://www.expedia.com"
}

# ================================
# TIMEOUTS - أوقات انتظار العمليات (بالثواني)
# ================================
SSE_STREAM_TIMEOUT = int(os.getenv("SSE_STREAM_TIMEOUT", "120"))  # اختياري: تحديث الانتظار
SSE_MAX_WAIT = int(os.getenv("SSE_MAX_WAIT", "60"))  # أقصى وقت للانتظار على البيانات
API_REQUEST_TIMEOUT = int(os.getenv("API_REQUEST_TIMEOUT", "30"))
BROWSER_LOAD_TIMEOUT = int(os.getenv("BROWSER_LOAD_TIMEOUT", "45"))

# ================================
# PRICE MONITORING THRESHOLDS - عتبات المراقبة
# ================================
MIN_SAVINGS_THRESHOLD = float(os.getenv("MIN_SAVINGS_THRESHOLD", "10"))  # الحد الأدنى للتوفير (دولار)
CANCELLATION_FEE_ESTIMATE = float(os.getenv("CANCELLATION_FEE_ESTIMATE", "0"))  # رسم الإلغاء المتوقع
REBOOKING_FEE_ESTIMATE = float(os.getenv("REBOOKING_FEE_ESTIMATE", "0"))  # رسم إعادة الحجز المتوقع
PRICE_CONFIDENCE_MIN = float(os.getenv("PRICE_CONFIDENCE_MIN", "0.75"))  # الحد الأدنى لثقة السعر

# ================================
# RETRY LOGIC - منطق إعادة المحاولة
# ================================
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))  # أقصى عدد محاولات
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", "2"))  # عامل التأخير الأسي
INITIAL_RETRY_DELAY = float(os.getenv("INITIAL_RETRY_DELAY", "1"))  # التأخير الأول (ثانية)

# ================================
# LOGGING - إعدادات السجلات
# ================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = LOGS_DIR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ================================
# CACHING - تخزين مؤقت للنتائج
# ================================
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
CACHE_EXPIRY_MINUTES = int(os.getenv("CACHE_EXPIRY_MINUTES", "30"))  # صلاحية الذاكرة المؤقتة

# ================================
# MOCK MODE - تشغيل وضع محاكاة (عندما يكون TinyFish معطل)
# ================================
USE_MOCK_PRICES = os.getenv("USE_MOCK_PRICES", "false").lower() == "true"
MOCK_PRICE_VARIANCE = float(os.getenv("MOCK_PRICE_VARIANCE", "0.25"))  # ±25% تباين السعر