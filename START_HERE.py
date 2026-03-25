#!/usr/bin/env python3
"""
RefundFish - Quick Start Guide
Everything you need to get running in 60 seconds
"""

STARTUP_GUIDE = """
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║        🐠 RefundFish - AI Hotel Price Monitor 🐠             ║
║                                                                ║
║            Ready to Find Hotel Refund Opportunities            ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ QUICK START (Choose One):

1️⃣  WEB DASHBOARD (Recommended)
   ───────────────────────────────
   Windows:    run_web.bat
   Mac/Linux:  bash run_web.sh
   
   Then open: http://localhost:5000
   
   ✓ Beautiful dashboard
   ✓ Configure settings
   ✓ Real-time search
   ✓ View history

2️⃣  COMMAND LINE
   ──────────────
   python main.py
   
   ✓ Simple terminal output
   ✓ Quick testing
   ✓ No UI overhead

3️⃣  VERIFY SETUP
   ──────────────
   python setup_check.py
   
   ✓ Check dependencies
   ✓ Verify configuration
   ✓ Validate structure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 WHAT YOU'LL NEED:

✓ TinyFish API Key      - In .env file ✓
✓ Python 3.8+          - Should already have ✓
✓ Internet Connection   - For web searches ✓
✓ TinyFish Credits      - Add at https://tinyfish.ai if needed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 HOW TO USE (Web Dashboard):

1. Open http://localhost:5000 in your browser

2. Fill in the hotel details:
   • Hotel Name: "Hilton Dubai"
   • Dates: "May 15-16 2026"
   • Price Paid: "194"

3. (Optional) Configure settings:
   • Min Savings: $10 (or adjust)
   • Website: Booking.com (or choose other)
   • Auto-refund: On/Off

4. Click "🔍 Search Price"

5. View results:
   • Current price found
   • Savings calculated
   • Recommendation shown
   • Added to history

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📂 KEY FILES:

Documentation:
  • README.md                 - Full documentation
  • PROJECT_SUMMARY.md        - Complete project overview
  • WEB_UI_GUIDE.md          - Web interface guide

Application:
  • app.py                    - Flask web server
  • main.py                   - CLI entry point
  • agents/browser_agent.py   - TinyFish integration

Web UI:
  • templates/index.html      - Dashboard HTML
  • static/app.js            - Interactive JavaScript
  • static/style.css         - Styling

Configuration:
  • .env                     - API keys & settings
  • config/settings.py       - App configuration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  COMMON ISSUES:

Problem: "Insufficient credits"
→ Add TinyFish credits at https://tinyfish.ai

Problem: "Port 5000 already in use"
→ Kill process on port 5000 or use different port

Problem: "No price found"
→ Try different website in settings
→ Verify hotel name spelling
→ Check TinyFish is working

Problem: Can't import module
→ Run: pip install -r requirements.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 FEATURES:

✓ Search hotel prices in real-time
✓ Calculate savings automatically
✓ Smart refund recommendations
✓ Adjustable thresholds
✓ Multiple website support
✓ Search history
✓ Live activity logs
✓ Professional web UI
✓ Settings persistence
✓ TinyFish AI integration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 TECH STACK:

Backend:     Python, Flask
Frontend:    HTML5, CSS3, JavaScript
AI:          TinyFish browser automation
Data:        JSON local storage
Logging:     Structured logging system

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 TIPS:

• Start with web dashboard for better experience
• Adjust savings threshold to your preference
• Check search history to compare results
• Monitor TinyFish credits usage
• Set auto-refund for convenience (if enabled)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 NEED HELP?

Read the documentation:
  • README.md              - Overview & setup
  • WEB_UI_GUIDE.md       - Dashboard guide
  • PROJECT_SUMMARY.md    - Complete details

Check the logs:
  • data/logs/app.log     - Application logs
  • Real-time logs in UI  - Live activity

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 READY TO START?

Run this now:

    run_web.bat              (Windows)
    bash run_web.sh          (Mac/Linux)
    python main.py           (CLI)

Then open: http://localhost:5000

Let's find you some refund opportunities! 🐠💰

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

if __name__ == "__main__":
    print(STARTUP_GUIDE)
