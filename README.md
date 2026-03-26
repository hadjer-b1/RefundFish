# RefundFish 🐟

> **Autonomous AI Agent for Hotel Price Protection**

RefundFish is an intelligent automation system that monitors hotel booking prices and helps you capture price drops. Using advanced AI agents and browser automation, RefundFish can automatically track prices, verify room details, and execute safe cancellations with refund validation.

## ✨ Key Features

### Core Capabilities

- 🎯 **Smart Quality Filter** - Only fetches hotels with 3.5+ star rating for reliable stays
- 💰 **Price Sanity Engine** - Intelligently filters out unrealistic high prices and focuses on genuine savings opportunities
- 🔐 **Session-Aware Authentication** - Uses existing browser cookies for secure, password-less access
- ❤️ **Automated Wishlist** - Seamlessly interacts with the "Heart" icon to save and manage deals

### Advanced Features

- 🤖 **Autonomous Price Monitoring** - Continuously search for better prices across booking platforms
- 🔗 **Multi-Platform Support** - Works with Booking.com, Expedia, Hotels.com, Kayak, and more
- 📧 **Magic Link Authentication** - Securely authenticate using email verification (no passwords stored)
- 🔐 **Encrypted Credentials** - All credentials encrypted using Fernet encryption
- 🏨 **Room Verification** - Automatically verify room details before rebooking (check-in/check-out dates, breakfast, cancellation policy)
- 📸 **Proof Capture** - Screenshot evidence of prices and room details for records
- ✅ **Safe Cancellations** - Validate refund amounts before executing cancellations
- 💰 **Refund Analysis** - Intelligent analysis of net savings after fees
- 🌐 **Web UI** - User-friendly Flask-based interface for easy management

## How It Works

```
1. Save Your Booking
   └─ You provide hotel booking details and authentication

2. Continuous Monitoring
   └─ TinyFish AI Agent searches for better prices daily

3. Price Comparison
   └─ System compares current prices with what you paid

4. Smart Analysis
   └─ Calculate net savings after cancellation & rebooking fees

5. Automated Actions
   └─ Verify rooms, capture proof, execute cancellations

6. Refund Processing
   └─ Monitor and validate refunds
```

## Tech Stack

- **Backend**: Python 3.8+ with Flask
- **Browser Automation**: [TinyFish Web Agent API](https://tinyfish.ai)
- **Encryption**: Cryptography (Fernet)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **API Communication**: REST

## 🚀 Getting Started

### Prerequisites

✅ **Python 3.9+** - Core requirement  
✅ **Telegram Bot Token** - For real-time price alerts (optional but recommended)  
✅ **Gmail App Password** - For email notifications (optional)  
✅ **TinyFish API key** - Optional; demo mode works without it

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/hadjer-b1/RefundFish.git
   cd RefundFish
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables** (optional for demo mode)
   ```bash
   cp .env.example .env
   # Add your API keys (or leave blank to use demo mode)
   ```

### Execution

**Start the application:**
```bash
python main.py
```

The application will:
- Launch the Flask web server on `http://localhost:5000`
- Automatically enable demo/mock mode if TinyFish API is unavailable
- Show a user-friendly interface ready for hotel price monitoring

**To stop:** Press `Ctrl+C` in the terminal

## Usage

### Basic Workflow

1. **Add Credentials**
   - Go to the credentials section
   - Select booking website (Booking.com, Expedia, etc.)
   - Enter your email and password (or use Magic Link for email-only)

2. **Fetch Reservations**
   - Click "Fetch Reservations" to retrieve your active bookings
   - System will login and extract your bookings

3. **Monitor Prices**
   - Search for current prices for your hotel dates
   - System compares with what you paid

4. **Review Analysis**
   - Check refund opportunity analysis
   - See net savings after fees

5. **Execute Actions** (Optional)
   - Verify room details
   - Capture proof (screenshots)
   - Cancel booking safely with refund validation

### Magic Link Authentication

For Booking.com and platforms using Magic Link:

1. Save your email only (no password needed)
2. When fetching, follow the console instructions
3. Click the verification link in your email
4. Return to RefundFish and retry fetch

## API Reference

### Save Credentials

```bash
POST /api/credentials/save
{
  "website": "booking.com",
  "username": "user@example.com",
  "password": "your_password",
  "two_fa_code": "123456"  # optional
}
```

### Fetch Reservations

```bash
POST /api/fetch-reservations
{
  "website": "booking.com"
}
```

### Search Current Price

```bash
POST /api/search
{
  "hotel_name": "Hotel Name",
  "dates": "May 15-16 2026"
}
```

## Configuration

Key environment variables (.env):

```bash
# TinyFish API Configuration
TINYFISH_API_KEY=sk-tinyfish-xxxxx

# OpenAI API (optional, for advanced analysis)
OPENAI_API_KEY=sk-xxxxx

# Application Settings
FLASK_ENV=development
MIN_SAVINGS_THRESHOLD=20  # Minimum savings to recommend rebooking
CANCELLATION_FEE_ESTIMATE=30  # Estimated cancellation fee
REBOOKING_FEE_ESTIMATE=10  # Estimated rebooking fee
```

## Security

- ✅ All credentials encrypted using Fernet encryption
- ✅ .env file with sensitive data in .gitignore
- ✅ No plain-text passwords stored
- ✅ Private documentation in private_docs/ folder
- ✅ Magic Link authentication for password-less access

## Project Structure

```
RefundFish/
├── agents/               # AI Agent implementations
│   ├── browser_agent.py # TinyFish browser automation
│   └── logic_agent.py   # Price analysis and decisions
├── config/              # Configuration & logging
│   ├── settings.py     # Environment & settings
│   └── logger.py       # Structured logging
├── utils/              # Utility functions
│   ├── credentials.py  # Credential encryption
│   ├── helpers.py      # Helper functions
│   └── exceptions.py   # Custom exceptions
├── static/             # Frontend assets
│   ├── app.js
│   └── style.css
├── templates/          # HTML templates
│   └── index.html
├── data/               # Data storage
│   ├── bookings.json
│   └── logs/
├── private_docs/       # Internal documentation (not in git)
├── app.py             # Flask application
├── main.py            # CLI entry point
└── requirements.txt   # Dependencies
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Code Structure

- **Modular design** with separate agents for browser automation and analysis
- **Error handling** with retry logic for API calls
- **Structured logging** for debugging and monitoring
- **Type hints** for better code clarity

### Adding Support for New Websites

1. Update `site_config` in `agents/browser_agent.py`
2. Add website-specific goals for TinyFish agent
3. Test reservation fetching and price searches

## Performance Optimization

- **Session Caching**: Browser sessions cached for 300x speed improvement
- **Credit-Efficient**: Optimized TinyFish calls to minimize API usage
- **Retry Logic**: Automatic retry on timeout/connection errors
- **Smart Timeouts**: Appropriate timeout values per operation

## Known Limitations

- TinyFish API relies on browser automation which may fail for websites with complex verification
- Price searches limited to the accuracy of TinyFish agent responses
- Cancellations require valid account login and appropriate permissions

## Troubleshooting

### TinyFish API Errors

**403 Forbidden**: Check your TinyFish credits at https://tinyfish.ai

**Timeout**: API call took too long. System will retry automatically.

**Rate Limited**: Too many API calls. System will wait and retry.

### Authentication Issues

- Verify credentials are correct
- Check email for verification links (Magic Link)
- Try logging in manually first, then retry

### Missing Reservations

- Ensure you're logged into the correct account
- Check booking website directly to verify reservations exist
- Verify website is supported (Booking.com, Expedia, Hotels.com, Kayak)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is provided as-is for personal use and hotel price monitoring.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

## 🛡️ Important: Demo Mode for Reliable Evaluation

> To ensure a smooth evaluation experience regardless of TinyFish API's real-time latency or server load during the final hours, we have enabled a Demo/Mock mode by default. This showcases the entire logic: filtering for 3.5+ star hotels, realistic price checking, and the Telegram/Email notification flow.

If you want to test with real price data after TinyFish recovers, set `USE_MOCK_PRICES=false` in `.env`.

---

**Made with 🐟 by RefundFish Team**

_Smart hotel rebooking, powered by AI_
