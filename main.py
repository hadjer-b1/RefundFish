"""
main.py
RefundFish Main Entry Point
Orchestrates price search and rebooking analysis
"""

import json
from agents.browser_agent import get_current_price
from agents.logic_agent import evaluate_refund_opportunity, get_detailed_analysis
from config.logger import setup_logger

logger = setup_logger("main")

def main():
    """Main RefundFish workflow"""
    
    print("="*60)
    print("RefundFish - Hotel Price & Rebooking Monitor")
    print("="*60)
    
    try:
        # Load booking data
        logger.info("Loading booking data...")
        with open('data/bookings.json', 'r') as f:
            booking = json.load(f)
        
        hotel = booking['hotel_name']
        dates = booking['dates']
        paid_price = booking['paid_price']
        
        print(f"\nBooking Details:")
        print(f"  Hotel: {hotel}")
        print(f"  Dates: {dates}")
        print(f"  Paid Price: ${paid_price}")
        
        # Get current price
        logger.info(f"Searching for current price of {hotel}...")
        current_price = get_current_price(hotel, dates)
        
        if current_price is None:
            print("\nError: Could not get current price")
            logger.error("Failed to get current price")
            return
        
        print(f"\nPrice Search:")
        print(f"  Current Price: ${current_price}")
        
        # Analyze opportunity
        logger.info("Analyzing rebooking opportunity...")
        should_rebook, savings = evaluate_refund_opportunity(current_price, paid_price)
        analysis = get_detailed_analysis(current_price, paid_price)
        
        print(f"\nAnalysis:")
        print(f"  Gross Savings: ${analysis['gross_savings']:.2f}")
        print(f"  Savings %: {analysis['savings_percent']:.1f}%")
        print(f"  Net Savings (after fees): ${savings:.2f}")
        
        # Recommendation
        print(f"\nRecommendation:")
        if should_rebook:
            print(f"  YES - Rebook! Save ${savings:.2f}")
            logger.info(f"Rebook recommended - savings: ${savings:.2f}")
        else:
            print(f"  NO - Savings too low: ${savings:.2f}")
            logger.info(f"Rebook not recommended - savings: ${savings:.2f}")
        
        print("="*60)
        
    except FileNotFoundError:
        print("\nError: data/bookings.json not found")
        logger.error("Booking file not found")
    except Exception as e:
        print(f"\nError: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)

if __name__ == "__main__":
    main()