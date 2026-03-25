#!/usr/bin/env python3
"""
RefundFish - Quick Setup & Test Script
Verifies all components are working correctly
"""

import os
import sys
import json
from pathlib import Path

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_item(status, text):
    symbol = "✓" if status else "✗"
    print(f"  {symbol} {text}")

def check_dependencies():
    """Check if all dependencies are installed"""
    print_header("Checking Dependencies")
    
    deps = {
        "requests": "HTTP requests",
        "flask": "Web server",
        "flask_cors": "CORS support",
        "dotenv": "Environment variables"
    }
    
    for module, desc in deps.items():
        try:
            __import__(module.replace("_", "-"))
            print_item(True, f"{module} ({desc})")
        except ImportError:
            print_item(False, f"{module} ({desc})")
            return False
    
    return True

def check_structure():
    """Check if directory structure is correct"""
    print_header("Checking Project Structure")
    
    dirs = [
        "agents", "config", "utils", "data", "templates", "static"
    ]
    
    all_ok = True
    for d in dirs:
        exists = Path(d).exists()
        print_item(exists, f"/{d}/")
        if not exists:
            all_ok = False
    
    return all_ok

def check_files():
    """Check if all required files exist"""
    print_header("Checking Core Files")
    
    files = [
        ("main.py", "CLI entry point"),
        ("app.py", "Flask web server"),
        ("requirements.txt", "Dependencies"),
        (".env", "Environment config"),
        ("agents/browser_agent.py", "TinyFish agent"),
        ("agents/logic_agent.py", "Analysis engine"),
        ("config/settings.py", "Configuration"),
        ("config/logger.py", "Logging"),
        ("templates/index.html", "Web UI"),
        ("static/app.js", "JavaScript"),
        ("static/style.css", "Styling"),
    ]
    
    all_ok = True
    for filepath, desc in files:
        exists = Path(filepath).exists()
        print_item(exists, f"{filepath} ({desc})")
        if not exists:
            all_ok = False
    
    return all_ok

def check_env():
    """Check if environment variables are set"""
    print_header("Checking Environment")
    
    from pathlib import Path
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    api_key = os.getenv("TINYFISH_API_KEY")
    if api_key:
        print_item(True, f"TINYFISH_API_KEY configured ({api_key[:20]}...)")
    else:
        print_item(False, "TINYFISH_API_KEY not set")
        return False
    
    return True

def check_imports():
    """Check if Python modules can be imported"""
    print_header("Checking Imports")
    
    try:
        from config.settings import TINYFISH_API_KEY
        print_item(True, "config.settings")
    except Exception as e:
        print_item(False, f"config.settings: {e}")
        return False
    
    try:
        from agents.browser_agent import get_current_price
        print_item(True, "agents.browser_agent")
    except Exception as e:
        print_item(False, f"agents.browser_agent: {e}")
        return False
    
    try:
        from agents.logic_agent import evaluate_refund_opportunity
        print_item(True, "agents.logic_agent")
    except Exception as e:
        print_item(False, f"agents.logic_agent: {e}")
        return False
    
    try:
        from app import app
        print_item(True, "Flask app (app.py)")
    except Exception as e:
        print_item(False, f"Flask app: {e}")
        return False
    
    return True

def show_usage():
    """Show usage instructions"""
    print_header("How to Use")
    
    print("\n📋 Option 1: Command Line")
    print("  python main.py")
    
    print("\n🌐 Option 2: Web UI (Recommended)")
    print("  Windows: run_web.bat")
    print("  Mac/Linux: bash run_web.sh")
    print("  Then open: http://localhost:5000")
    
    print("\n📖 Documentation")
    print("  - README.md: Full project documentation")
    print("  - WEB_UI_GUIDE.md: Web interface guide")
    print("  - agents/browser_agent.py: Agent implementation")

def main():
    print("\n")
    print("██████╗ ███████╗███████╗██╗   ██╗███╗   ██╗██████╗ ███████╗██╗███████╗██╗  ██╗")
    print("██╔══██╗██╔════╝██╔════╝██║   ██║████╗  ██║██╔══██╗██╔════╝██║██╔════╝██║  ██║")
    print("██████╔╝█████╗  █████╗  ██║   ██║██╔██╗ ██║██║  ██║█████╗  ██║███████╗███████║")
    print("██╔══██╗██╔══╝  ██╔══╝  ██║   ██║██║╚██╗██║██║  ██║██╔══╝  ██║╚════██║██╔══██║")
    print("██║  ██║███████╗██║     ╚██████╔╝██║ ╚████║██████╔╝███████╗██║███████║██║  ██║")
    print("╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝╚══════╝╚═╝  ╚═╝")
    print("AI Hotel Price Monitor - TinyFish Competition 2026")
    
    results = []
    
    results.append(("Dependencies", check_dependencies()))
    results.append(("Structure", check_structure()))
    results.append(("Files", check_files()))
    results.append(("Environment", check_env()))
    results.append(("Imports", check_imports()))
    
    print_header("Setup Summary")
    
    all_ok = True
    for name, ok in results:
        print_item(ok, name)
        if not ok:
            all_ok = False
    
    show_usage()
    
    if all_ok:
        print_header("✓ All checks passed!")
        print("\n🚀 Ready to start RefundFish!")
        print("   Choose an option above to begin.\n")
    else:
        print_header("⚠️ Some checks failed")
        print("\n  Please fix the issues above and try again.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
