# Internship/Attachment Outreach Agent — Setup Guide

## Prerequisites
- Python 3.10 or higher
- Ollama installed and running
- A Google account (Gmail)
- Your CV as a PDF file

---

## Step 1: Create a Google Cloud Platform Project (Free)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **"Select a Project"** → **"New Project"**
3. Name it: `attachment-outreach-agent`
4. Click **"Create"**
5. Make sure the new project is selected in the top bar

---

## Step 2: Enable Required APIs

In the Google Cloud Console, go to **APIs & Services → Library** and enable these three APIs:

1. **Places API (New)**
   - Search for "Places API (New)" and click **Enable**
   
2. **Gmail API**
   - Search for "Gmail API" and click **Enable**
   
3. **Google Sheets API**
   - Search for "Google Sheets API" and click **Enable**

---

## Step 3: Create an API Key (for Places API)

1. Go to **APIs & Services → Credentials**
2. Click **"+ CREATE CREDENTIALS" → "API Key"**
3. Copy the API key
4. Click **"Edit API Key"** (optional but recommended):
   - Under "API restrictions", select **"Restrict key"**
   - Choose **"Places API (New)"** only
   - Click **Save**
5. You'll enter this key during the setup wizard

---

## Step 4: Create OAuth 2.0 Credentials (for Gmail & Sheets)

1. Go to **APIs & Services → Credentials**
2. Click **"+ CREATE CREDENTIALS" → "OAuth client ID"**
3. If prompted, configure the **OAuth consent screen**:
   - User Type: **External**
   - App name: `Attachment Outreach Agent`
   - User support email: your Gmail
   - Developer contact email: your Gmail
   - Click **Save and Continue** through all steps
   - On the **"Test users"** page, click **"+ ADD USERS"** and add your Gmail address
   - Click **Save and Continue**, then **Back to Dashboard**
4. Now create the OAuth client:
   - Application type: **Desktop app**
   - Name: `Attachment Agent Desktop`
   - Click **Create**
5. Click **"DOWNLOAD JSON"** to download the credentials file
6. Rename it to `credentials.json`
7. Move it to: `credentials/credentials.json` (replacing the example file)

---

## Step 5: Set Up Ollama

1. Install Ollama from [ollama.ai](https://ollama.ai)
2. Make sure Ollama is running: `ollama serve`
3. Pull a model for email writing:
   ```bash
   ollama pull mistral:7b
   ```
   Or other options:
   ```bash
   ollama pull llama3.1       # Larger, better quality
   ollama pull qwen2.5:7b     # Good alternative
   ```
4. Verify it works:
   ```bash
   ollama run mistral:7b "Hello, write me a one-sentence professional greeting."
   ```

---

## Step 6: Prepare Your CV

1. Make sure your CV is in PDF format
2. Copy it to: `data/your_cv.pdf`
3. If you use a different filename, update `CV_PATH` in `config.py`

---

## Step 7: Install Python Dependencies

Open a terminal in the project directory and run:

```bash
pip install -r requirements.txt
```

---

## Step 8: Run the Setup Wizard

```bash
python main.py setup
```

This will ask you for:
- Your full name
- Your Gmail address
- Your phone number (optional)
- Your skills
- Your Google API key (from Step 3)
- Your Ollama model preference
- Email settings

All settings are saved to `config.json`.

---

## Step 9: Run the Agent!

```bash
# Full pipeline (discover → extract emails → compose → draft → track)
python main.py run

# Or run individual steps:
python main.py scout      # Find companies
python main.py hunt       # Extract emails
python main.py compose    # Write emails with AI
python main.py draft      # Create Gmail drafts
python main.py track      # Sync to Google Sheet
```

---

## Step 10: Review and Send

1. Open your Gmail → **Drafts** folder
2. Review the drafted emails
3. When satisfied, send them:
   ```bash
   python main.py send          # Send all drafts (with throttling)
   python main.py send --id 5   # Send a specific draft
   ```

---

## Step 11: Set Up Daily Follow-ups

### Option A: Run Manually
```bash
python main.py followup        # Check for responses & create follow-up drafts
python main.py followup --auto # Auto-send follow-ups (skip draft review)
```

### Option B: Windows Task Scheduler (Automatic)
1. Open **Task Scheduler** (search in Start menu)
2. Click **"Create Basic Task"**
3. Name: `Attachment Outreach Follow-up`
4. Trigger: **Daily**, at a time that works for you (e.g., 9:00 AM)
5. Action: **Start a program**
   - Program: `python`
   - Arguments: `main.py followup --auto`
   - Start in: `<path to your project folder>`
6. Click **Finish**

### Option C: Linux/Mac Cron Job (Automatic)
```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 9:00 AM):
0 9 * * * cd /path/to/project && python main.py followup --auto
```

---

## Troubleshooting

### "OAuth consent screen not configured"
- Go to APIs & Services → OAuth consent screen → Make sure it's published or you're added as a test user

### "API key not valid"
- Make sure Places API (New) is enabled for your project
- Check that the API key isn't restricted to a different API

### "Ollama connection refused"
- Run `ollama serve` in a separate terminal
- Make sure the model is pulled: `ollama list`

### "Gmail quota exceeded"
- You've hit the daily sending limit (500 for free Gmail)
- Wait 24 hours and try again
- The agent will automatically resume where it left off

### "No emails found for companies"
- This is normal — not all companies list emails publicly
- The agent will try multiple methods (website crawling, pattern guessing)
- You can manually add emails to the database or Google Sheet
