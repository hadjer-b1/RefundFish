"""
agents/logic_agent.py
RefundFish - Decision Analysis Engine
Analyzes prices and recommends rebooking
"""

from typing import Tuple, Dict, Any
from config.settings import MIN_SAVINGS_THRESHOLD, CANCELLATION_FEE_ESTIMATE, REBOOKING_FEE_ESTIMATE
from config.logger import setup_logger

logger = setup_logger("logic_agent")

def evaluate_refund_opportunity(current_price: float, paid_price: float, 
                               threshold: float = MIN_SAVINGS_THRESHOLD) -> Tuple[bool, float]:
    """
    Decide if rebooking is worth it based on price savings
    
    Args:
        current_price: Current hotel price
        paid_price: Price already paid
        threshold: Minimum savings in USD
    
    Returns:
        (should_rebook: bool, net_savings: float)
    """
    
    # Calculate savings
    gross_savings = paid_price - current_price
    total_fees = CANCELLATION_FEE_ESTIMATE + REBOOKING_FEE_ESTIMATE
    net_savings = gross_savings - total_fees
    
    logger.info(f"Price Analysis:")
    logger.info(f"  Old Price: ${paid_price}")
    logger.info(f"  New Price: ${current_price}")
    logger.info(f"  Gross Savings: ${gross_savings:.2f}")
    logger.info(f"  Total Fees: ${total_fees:.2f}")
    logger.info(f"  Net Savings: ${net_savings:.2f}")
    logger.info(f"  Threshold: ${threshold}")
    
    should_rebook = net_savings >= threshold
    
    if should_rebook:
        logger.info(f"RECOMMEND: Rebook (save ${net_savings:.2f})")
    else:
        logger.info(f"DO NOT REBOOK: Savings too low (${net_savings:.2f})")
    
    return should_rebook, net_savings

def get_detailed_analysis(current_price: float, paid_price: float) -> Dict[str, Any]:
    """Get detailed analysis of rebooking opportunity"""
    
    should_rebook, net_savings = evaluate_refund_opportunity(current_price, paid_price)
    
    gross_savings = paid_price - current_price
    savings_percent = ((paid_price - current_price) / paid_price * 100) if paid_price > 0 else 0
    
    return {
        "should_rebook": should_rebook,
        "net_savings": net_savings,
        "gross_savings": gross_savings,
        "savings_percent": savings_percent,
        "old_price": paid_price,
        "new_price": current_price,
        "total_fees": CANCELLATION_FEE_ESTIMATE + REBOOKING_FEE_ESTIMATE,
        "confidence": 0.9 if should_rebook else 0.5
    }

__all__ = ['evaluate_refund_opportunity', 'get_detailed_analysis']