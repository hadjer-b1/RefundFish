"""
utils/exceptions.py
===================
Custom exceptions for RefundFish project
Each error in the project raises one of these exception types
"""

class RefundFishException(Exception):
    """Base exception for all RefundFish errors"""
    pass

class PriceExtractionError(RefundFishException):
    """Failed to extract price from browser agent response"""
    pass

class BrowserAgentError(RefundFishException):
    """Error in browser agent (SSE stream timeout, connection error, etc.)"""
    pass

class TinyFishAPIError(RefundFishException):
    """Error from TinyFish API service"""
    pass

class BookingNotFoundError(RefundFishException):
    """Requested booking not found in system"""
    pass

class CancellationError(RefundFishException):
    """Failed to cancel booking"""
    pass

class RebookingError(RefundFishException):
    """Failed to rebook with new price"""
    pass

class InsufficientSavingsError(RefundFishException):
    """Savings amount is below minimum threshold"""
    pass

class ConfigurationError(RefundFishException):
    """Configuration error (missing API keys, invalid settings, etc.)"""
    pass

