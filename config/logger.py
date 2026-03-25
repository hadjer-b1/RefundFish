"""
config/logger.py
================
Centralized logging system with structured logging
All modules use this logger instead of print()
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from config import settings

class ConsoleFormatter(logging.Formatter):
    """Custom formatter for console output"""
    
    def format(self, record):
        # Add timestamp and log level
        return super().format(record)

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger for any module
    Example: logger = setup_logger("browser_agent")
    """
    logger = logging.getLogger(name)
    
    # Set log level
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(log_level)
    
    # Prevent duplicate log entries
    if logger.hasHandlers():
        return logger
    
    # Console handler (prints to screen)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(settings.LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (saves to log file)
    log_file = settings.LOG_DIR / f"{name}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)
    
    return logger

# Logger مركزي للتطبيق
main_logger = setup_logger("refundfish")

def log_event(event_type: str, data: dict):
    """
    تسجيل حدث مهم بصيغة JSON
    استخدام: log_event("price_found", {"hotel": "Hilton", "price": 150})
    """
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **data
    }
    main_logger.info(json.dumps(event, ensure_ascii=False))

