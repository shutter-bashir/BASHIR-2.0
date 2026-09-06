# 🎓 Internship/Attachment Outreach Agent

> **An AI-powered multi-agent system that automates your internship/attachment search** — from discovering companies to sending personalized emails and tracking responses.

Built for university students in Kenya (and beyond) who need to find industrial attachment and internship placements. Instead of manually searching for companies and sending emails one by one, this agent does it all for you.

---

##  What It Does

Scout    →  Discovers IT companies near you using Google Maps
Hunt     →  Extracts contact emails from company websites  
Compose  →  Writes personalized emails using AI (Ollama)
Draft    →  Creates Gmail drafts with your CV attached
Track    →  Syncs everything to a live Google Sheet Follow-up →  Auto-sends follow-ups after 4 days
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Main Orchestrator                  │
│                     (main.py)                        │
├────────┬────────┬────────┬────────┬────────┬────────┤
│ Scout  │ Hunter │Composer│ Mailer │Tracker │FollowUp│
│ Agent  │ Agent  │ Agent  │ Agent  │ Agent  │ Agent  │
├────────┴────────┴────────┴────────┴────────┴────────┤
│              SQLite Database (data/)                  │
├─────────────────────────────────────────────────────┤
│   Google Maps API  │  Gmail API  │ Google Sheets API │
│                    │   Ollama    │                    │
└─────────────────────────────────────────────────────┘
```

##Quick Start

### 1. Clone this repository
```bash
git clone 
cd attachment-outreach-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up your APIs
Follow the detailed instructions in **[setup_guide.md](setup_guide.md)** to:
- Create a Google Cloud project (free)
- Get your Google Places API key
- Set up Gmail & Sheets OAuth credentials
- Install and configure Ollama 

{models >Qwen2.5-Coder 1.5B	~1 GB
         Phi-3 Mini	~2.2 GB
        Qwen3 Coder	varies greatly
        Mistral 7B}

### 4. Add your CV
```bash
# Copy your CV to the data folder
cp /path/to/your_cv.pdf data/your_cv.pdf
```

### 5. Run the setup wizard
```bash
python main.py setup
```

### 6. Launch the agent!
```bash
python main.py run
```

---

## 📖 Usage

### Full Pipeline
```bash
python main.py run            # Run everything: scout → hunt → compose → draft → track
```

### Individual Steps
```bash
python main.py scout          # 🔍 Search for IT companies
python main.py hunt           # 📧 Extract emails from websites
python main.py compose        # ✍️ Write personalized emails with AI
python main.py draft          # 📬 Create Gmail drafts with CV attached
python main.py track          # 📊 Sync to Google Sheet
python main.py followup       # 🔄 Check responses & send follow-ups
```

### Monitoring & Control
```bash
python main.py status         # 📈 View pipeline statistics
python main.py review         # 📋 List drafts ready for review
python main.py send           # 📤 Send approved drafts
python main.py test           # 🧪 Test all API connections
```

### Options
```bash
python main.py scout --dry-run        # Test with 1 query only
python main.py hunt --limit 10        # Process only 10 companies
python main.py send --id 5            # Send a specific draft
python main.py followup --auto        # Auto-send follow-ups
```

---

## ⚙️ Configuration

All settings are in **`config.json`**. Edit it directly or use `python main.py setup`.

### Your Profile
```json
{
    "student": {
        "name": "YOUR FULL NAME",
        "email": "your.email@gmail.com",
        "phone": "+254700000000",
        "course": "BSc Computer Science",
        "university": "Your University Name",
        "year": 3,
        "skills": ["Python", "JavaScript", "SQL", "Git"],
        "attachment_start": "January 2027",
        "attachment_end": "March 2027"
    }
}
```

### Search Zones
Customize the geographic zones to search for companies in your city:
```json
{
    "search": {
        "zones": [
            {
                "name": "Your City Center",
                "latitude": -1.2864,
                "longitude": 36.8172,
                "radius_meters": 3000
            }
        ]
    }
}
```

### Email Settings
```json
{
    "email": {
        "daily_send_limit": 50,
        "throttle_min_seconds": 30,
        "throttle_max_seconds": 90,
        "max_followups": 2,
        "followup_interval_days": 4
    }
}
```

---

## 📁 Project Structure

```
attachment-outreach-agent/
├── main.py                  # CLI orchestrator
├── config.py                # Configuration management
├── config.json              # Your settings (edit this!)
├── requirements.txt         # Python dependencies
├── setup_guide.md           # Detailed setup instructions
├── LICENSE                  # MIT License
│
├── agents/                  # AI agent modules
│   ├── scout.py             # Google Maps company discovery
│   ├── hunter.py            # Email extraction from websites
│   ├── composer.py          # AI email composition (Ollama)
│   ├── mailer.py            # Gmail draft creation & sending
│   ├── tracker.py           # Google Sheets sync
│   └── followup.py          # Response checking & follow-ups
│
├── core/                    # Core utilities
│   ├── database.py          # SQLite database management
│   ├── models.py            # Data models (Company, Email, Draft)
│   ├── gmail_auth.py        # Gmail OAuth authentication
│   └── sheets_auth.py       # Sheets OAuth authentication
│
├── templates/               # AI prompt templates
│   ├── email_prompt.txt     # Initial email prompt
│   └── followup_prompt.txt  # Follow-up email prompt
│
├── credentials/             # OAuth credentials (gitignored)
│   └── credentials.json     # Your Google OAuth file
│
└── data/                    # Runtime data (gitignored)
    ├── your_cv.pdf          # Your CV
    ├── outreach.db          # SQLite database (auto-created)
    └── search_queries.json  # Categorized search queries
```

---

## 🔧 How to Customize

### For Your University
1. Edit `config.json` → update your name, email, university, course, and skills
2. Replace `data/your_cv.pdf` with your own CV

### For Your City
1. Edit `config.json` → update the `search.zones` with your city's coordinates
2. Use [Google Maps](https://maps.google.com) to find latitude/longitude for areas you want to search

### Email Templates
1. Edit `templates/email_prompt.txt` to customize how emails are written
2. Edit `templates/followup_prompt.txt` for follow-up style

### AI Model
1. Edit `config.json` → change `ollama.model` to your preferred model
2. Recommended: `mistral:7b`, `llama3.1`, `qwen2.5:7b`

---

## 🛡️ Safety Features

- **Draft Mode**: Emails are created as Gmail drafts first — you review before sending
- **Daily Limits**: Configurable daily send limit (default: 50) to avoid Gmail throttling
- **Smart Throttling**: Random delays between sends (30-90 seconds) to look natural
- **Duplicate Detection**: Won't re-contact companies already in your database
- **Bounce Detection**: Automatically detects bounced emails
- **Max Follow-ups**: Limits follow-ups to 2 per company (configurable)

---

## 📊 Pipeline Statistics

Run `python main.py status` to see your progress:

```
┌─────────────────────────────────┬───────┬────────────┐
│ Stage                           │ Count │ Status     │
├─────────────────────────────────┼───────┼────────────┤
│ 🔍 Companies Discovered        │   150 │ ████       │
│ 📧 Emails Extracted            │    89 │ ███        │
│ ✍️ Emails Composed             │    89 │ ███        │
│ 📬 Drafts Created              │    89 │ ███        │
│ 📤 Emails Sent                 │    75 │ ███        │
│ 🔄 Follow-up 1 Sent            │    30 │ █          │
│ ✅ Responses Received           │    12 │            │
└─────────────────────────────────┴───────┴────────────┘

📊 Response Rate: 16.0% (12/75)
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Add support for other email providers
- Add new search regions/countries
- Improve email templates
- Add support for other LLM providers (OpenAI, Anthropic, etc.)
- Create a web dashboard

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This tool is designed to help students find legitimate internship opportunities. Please use it responsibly:
- Always review drafted emails before sending
- Respect companies that opt out or don't respond
- Follow Gmail's terms of service and sending limits
- Be genuine in your applications

---

**Made with ❤️ to help students find their dream internship.**

*If this helped you land an attachment, please ⭐ star this repo!*
