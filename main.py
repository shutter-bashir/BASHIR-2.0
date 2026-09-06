#!/usr/bin/env python3
"""
Internship/Attachment Outreach Agent — Main Orchestrator

A multi-agent system that discovers IT companies in your city, extracts their
contact emails, composes personalized attachment request emails using a local
LLM (Ollama), creates Gmail drafts with your CV attached, tracks everything
in Google Sheets, and automatically follows up after 4 days.

Usage:
    python main.py setup          # Interactive setup wizard
    python main.py run            # Run full pipeline
    python main.py scout          # Only search for companies
    python main.py hunt           # Only extract emails
    python main.py compose        # Only compose emails with AI
    python main.py draft          # Only create Gmail drafts
    python main.py track          # Only sync to Google Sheet
    python main.py followup       # Check responses & send follow-ups
    python main.py status         # Show pipeline statistics
    python main.py review         # List drafts ready for review
    python main.py send           # Send all approved drafts
    python main.py test           # Test all API connections
"""

import os
import sys
import logging
import click
from pathlib import Path
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from config import (
    Config, load_config, save_config,
    PROJECT_DIR, DATA_DIR, CREDENTIALS_DIR, CV_PATH, DB_PATH,
    StudentProfile, OllamaConfig, EmailConfig
)
from core.database import Database
from core.models import CompanyStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("main")
console = Console()


def get_db(config: Config) -> Database:
    """Initialize and return the database."""
    return Database(config.db_path)


def print_banner():
    """Print the application banner."""
    banner = """
╔══════════════════════════════════════════════════════════╗
║       🎓 Internship/Attachment Outreach Agent            ║
║       Multi-Agent System for Industrial Attachment       ║
║                                                          ║
║  Scout → Hunt → Compose → Draft → Track → Follow-up     ║
╚══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


@click.group()
@click.pass_context
def cli(ctx):
    """Internship/Attachment Outreach Agent — Find IT companies, compose emails, and track outreach."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config()


@cli.command()
@click.pass_context
def setup(ctx):
    """Interactive setup wizard — configure your profile, API keys, and test connections."""
    print_banner()
    console.print("\n[bold green]🔧 Setup Wizard[/bold green]\n")
    
    config = ctx.obj['config']
    
    # Student Profile
    console.print("[bold]Step 1: Your Profile[/bold]", style="cyan")
    config.student.name = click.prompt("  Full Name", default=config.student.name)
    config.student.email = click.prompt("  Gmail Address", default=config.student.email)
    config.student.phone = click.prompt("  Phone Number (optional, press Enter to skip)", default=config.student.phone)
    
    skills_input = click.prompt(
        "  Key Skills (comma-separated)", 
        default=", ".join(config.student.skills)
    )
    config.student.skills = [s.strip() for s in skills_input.split(",")]
    
    console.print("\n[bold]Step 2: Google API Key[/bold]", style="cyan")
    console.print("  Get your API key from: [link]https://console.cloud.google.com/apis/credentials[/link]")
    config.google_api_key = click.prompt("  Google API Key", default=config.google_api_key)
    
    console.print("\n[bold]Step 3: Ollama Model[/bold]", style="cyan")
    config.ollama.model = click.prompt("  Ollama Model", default=config.ollama.model)
    
    console.print("\n[bold]Step 4: Email Settings[/bold]", style="cyan")
    config.email.daily_send_limit = click.prompt("  Daily send limit", default=config.email.daily_send_limit, type=int)
    config.email.followup_interval_days = click.prompt("  Follow-up interval (days)", default=config.email.followup_interval_days, type=int)
    
    # Save config
    save_config(config)
    console.print("\n[bold green]✅ Configuration saved to config.json[/bold green]")
    
    # Check prerequisites
    console.print("\n[bold]Checking prerequisites...[/bold]", style="cyan")
    
    # Check CV
    if CV_PATH.exists():
        console.print(f"  ✅ CV found: {CV_PATH}")
    else:
        console.print(f"  ⚠️  CV not found. Place your CV PDF at: [bold]{CV_PATH}[/bold]", style="yellow")
    
    # Check credentials
    creds_file = CREDENTIALS_DIR / "credentials.json"
    if creds_file.exists():
        console.print(f"  ✅ OAuth credentials found: {creds_file}")
    else:
        console.print(f"  ⚠️  OAuth credentials not found. Download from Google Cloud Console and place at: [bold]{creds_file}[/bold]", style="yellow")
    
    # Check Ollama
    try:
        import ollama
        models = ollama.list()
        model_names = [m.get('name', m.get('model', 'unknown')) for m in models.get('models', [])]
        if model_names:
            console.print(f"  ✅ Ollama running. Models: {', '.join(model_names)}")
        else:
            console.print(f"  ⚠️  Ollama running but no models found. Run: ollama pull {config.ollama.model}", style="yellow")
    except Exception as e:
        console.print(f"  ❌ Ollama not running: {e}", style="red")
    
    console.print("\n[bold green]Setup complete! Run 'python main.py run' to start the pipeline.[/bold green]\n")


@cli.command()
@click.option('--dry-run', is_flag=True, help='Test with 1 query in 1 zone only')
@click.pass_context
def scout(ctx, dry_run):
    """🔍 Search Google Maps for IT companies in Nairobi."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.scout import ScoutAgent
    
    console.print("\n[bold cyan]🔍 Scout Agent — Searching for IT companies in Nairobi...[/bold cyan]\n")
    agent = ScoutAgent(config, db)
    count = agent.run(dry_run=dry_run)
    console.print(f"\n[bold green]✅ Scout complete! Found {count} companies.[/bold green]\n")


@cli.command()
@click.option('--limit', default=0, help='Max companies to process (0 = all)')
@click.pass_context
def hunt(ctx, limit):
    """📧 Extract emails from company websites."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.hunter import HunterAgent
    
    console.print("\n[bold cyan]📧 Hunter Agent — Extracting emails from company websites...[/bold cyan]\n")
    agent = HunterAgent(config, db)
    count = agent.run(limit=limit)
    console.print(f"\n[bold green]✅ Hunt complete! Found emails for {count} companies.[/bold green]\n")


@cli.command()
@click.option('--limit', default=0, help='Max emails to compose (0 = all)')
@click.pass_context
def compose(ctx, limit):
    """✍️ Compose personalized emails using Ollama AI."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.composer import ComposerAgent
    
    console.print("\n[bold cyan]✍️ Composer Agent — Writing personalized emails with AI...[/bold cyan]\n")
    agent = ComposerAgent(config, db)
    count = agent.run(limit=limit)
    console.print(f"\n[bold green]✅ Composition complete! Composed {count} emails.[/bold green]\n")


@cli.command()
@click.option('--dry-run', is_flag=True, help='Test Gmail auth without creating drafts')
@click.option('--limit', default=0, help='Max drafts to create (0 = all)')
@click.pass_context
def draft(ctx, dry_run, limit):
    """📬 Create Gmail drafts with CV attached."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.mailer import MailerAgent
    
    console.print("\n[bold cyan]📬 Mailer Agent — Creating Gmail drafts...[/bold cyan]\n")
    agent = MailerAgent(config, db)
    
    if dry_run:
        console.print("[yellow]Dry run mode — testing Gmail connection only[/yellow]")
        try:
            from core.gmail_auth import GmailAuth
            auth = GmailAuth(
                config.credentials_dir / 'credentials.json',
                config.credentials_dir / 'token.json'
            )
            service = auth.get_service()
            if auth.test_connection():
                console.print("[bold green]✅ Gmail connection successful![/bold green]")
            else:
                console.print("[bold red]❌ Gmail connection failed[/bold red]")
        except Exception as e:
            console.print(f"[bold red]❌ Gmail auth error: {e}[/bold red]")
        return
    
    count = agent.create_drafts(limit=limit)
    console.print(f"\n[bold green]✅ Created {count} Gmail drafts. Check your Gmail Drafts folder![/bold green]\n")


@cli.command()
@click.option('--dry-run', is_flag=True, help='Test Sheets connection without writing data')
@click.pass_context
def track(ctx, dry_run):
    """📊 Sync all data to Google Sheet."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.tracker import TrackerAgent
    
    console.print("\n[bold cyan]📊 Tracker Agent — Syncing to Google Sheet...[/bold cyan]\n")
    agent = TrackerAgent(config, db)
    url = agent.run(dry_run=dry_run)
    console.print(f"\n[bold green]✅ Google Sheet updated![/bold green]")
    console.print(f"📋 Open your sheet: [link]{url}[/link]\n")


@cli.command()
@click.option('--auto', 'auto_send', is_flag=True, help='Auto-send follow-ups (skip draft review)')
@click.pass_context
def followup(ctx, auto_send):
    """🔄 Check for responses and send 4-day follow-ups."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.followup import FollowUpAgent
    
    console.print("\n[bold cyan]🔄 Follow-up Agent — Checking responses & sending follow-ups...[/bold cyan]\n")
    agent = FollowUpAgent(config, db)
    stats = agent.run(auto_send=auto_send)
    
    console.print(f"\n[bold green]✅ Follow-up check complete![/bold green]")
    console.print(f"  📥 Responses found: {stats.get('responses_found', 0)}")
    console.print(f"  ⛔ Bounced emails: {stats.get('bounced', 0)}")
    console.print(f"  📝 Follow-ups created: {stats.get('followups_created', 0)}")
    console.print(f"  📤 Follow-ups sent: {stats.get('followups_sent', 0)}\n")


@cli.command()
@click.pass_context
def status(ctx):
    """📈 Show pipeline statistics."""
    config = ctx.obj['config']
    db = get_db(config)
    
    print_banner()
    stats = db.get_pipeline_stats()
    
    table = Table(title="Pipeline Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Stage", style="cyan", width=25)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Status", width=15)
    
    stage_info = [
        (CompanyStatus.DISCOVERED, "🔍 Companies Discovered"),
        (CompanyStatus.EMAILS_FOUND, "📧 Emails Extracted"),
        (CompanyStatus.EMAIL_COMPOSED, "✍️ Emails Composed"),
        (CompanyStatus.DRAFT_CREATED, "📬 Drafts Created"),
        (CompanyStatus.SENT, "📤 Emails Sent"),
        (CompanyStatus.FOLLOWED_UP_1, "🔄 Follow-up 1 Sent"),
        (CompanyStatus.FOLLOWED_UP_2, "🔄 Follow-up 2 Sent"),
        (CompanyStatus.RESPONDED, "✅ Responses Received"),
        (CompanyStatus.NO_RESPONSE, "🔴 No Response"),
        (CompanyStatus.BOUNCED, "⛔ Bounced"),
    ]
    
    for status_enum, label in stage_info:
        count = stats.get(status_enum.value, 0)
        bar = "█" * min(count // 5, 20) if count > 0 else ""
        table.add_row(label, str(count), bar)
    
    console.print(table)
    
    # Response rate
    sent = stats.get(CompanyStatus.SENT.value, 0) + stats.get(CompanyStatus.FOLLOWED_UP_1.value, 0) + stats.get(CompanyStatus.FOLLOWED_UP_2.value, 0)
    responded = stats.get(CompanyStatus.RESPONDED.value, 0)
    if sent > 0:
        rate = (responded / sent) * 100
        console.print(f"\n📊 Response Rate: [bold green]{rate:.1f}%[/bold green] ({responded}/{sent})\n")


@cli.command()
@click.pass_context
def review(ctx):
    """📋 List all drafts ready for review."""
    config = ctx.obj['config']
    db = get_db(config)
    
    drafts = db.get_unsent_drafts()
    
    if not drafts:
        console.print("\n[yellow]No unsent drafts found. Run 'python main.py compose' and 'python main.py draft' first.[/yellow]\n")
        return
    
    table = Table(title=f"📋 {len(drafts)} Drafts Ready for Review", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", width=5)
    table.add_column("To", style="green", width=30)
    table.add_column("Subject", width=45)
    table.add_column("Status", width=15)
    
    for d in drafts:
        table.add_row(str(d.id), d.to_email, d.subject, d.status)
    
    console.print(table)
    console.print(f"\nTo send all: [bold]python main.py send[/bold]")
    console.print(f"To send one: [bold]python main.py send --id <ID>[/bold]\n")


@cli.command()
@click.option('--limit', default=50, help='Number of companies to list (default 50, 0 = all)')
@click.pass_context
def emails(ctx, limit):
    """📧 List extracted company email addresses."""
    config = ctx.obj['config']
    db = get_db(config)
    
    data = db.get_companies_with_emails()
    if not data:
        console.print("\n[yellow]No emails found yet. Run 'python main.py hunt' first.[/yellow]\n")
        return
        
    total_count = len(data)
    if limit > 0:
        data = data[:limit]
        
    table = Table(title=f"📧 Extracted Emails (Showing {len(data)} of {total_count} companies)", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Company Name", style="cyan", width=35)
    table.add_column("Email Address(es)", style="green", width=40)
    
    for idx, (company, email_list) in enumerate(data, 1):
        email_strs = ", ".join([e.email for e in email_list[:2]])
        table.add_row(str(idx), company.name, email_strs)
        
    console.print(table)
    console.print(f"\nRun [bold]python main.py track[/bold] to sync all to a Google Sheet!\n")


@cli.command()
@click.option('--id', 'draft_id', default=None, type=int, help='Send a specific draft by ID')
@click.option('--limit', default=0, help='Max emails to send (0 = all)')
@click.pass_context
def send(ctx, draft_id, limit):
    """📤 Send approved Gmail drafts with throttling."""
    config = ctx.obj['config']
    db = get_db(config)
    
    from agents.mailer import MailerAgent
    
    agent = MailerAgent(config, db)
    
    if draft_id:
        console.print(f"\n[cyan]📤 Sending draft #{draft_id}...[/cyan]")
        success = agent.send_draft(draft_id)
        if success:
            console.print(f"[bold green]✅ Draft #{draft_id} sent successfully![/bold green]\n")
        else:
            console.print(f"[bold red]❌ Failed to send draft #{draft_id}[/bold red]\n")
    else:
        console.print("\n[cyan]📤 Sending approved drafts with throttling...[/cyan]")
        if not click.confirm("  This will send unsent drafts. Continue?"):
            return
        count = agent.send_all_drafts(limit=limit)
        console.print(f"\n[bold green]✅ Sent {count} emails successfully![/bold green]\n")


@cli.command()
@click.pass_context
def run(ctx):
    """🚀 Run the full pipeline: scout → hunt → compose → draft → track."""
    config = ctx.obj['config']
    
    print_banner()
    
    # Validate setup
    issues = []
    if config.google_api_key == "YOUR_GOOGLE_API_KEY":
        issues.append("Google API key not set. Run 'python main.py setup' first.")
    if config.student.name == "YOUR NAME":
        issues.append("Student name not set. Run 'python main.py setup' first.")
    if not CV_PATH.exists():
        issues.append(f"CV not found at {CV_PATH}. Place your CV PDF there.")
    if not (CREDENTIALS_DIR / "credentials.json").exists():
        issues.append(f"OAuth credentials not found. See setup_guide.md for instructions.")
    
    if issues:
        console.print("[bold red]❌ Setup issues found:[/bold red]")
        for issue in issues:
            console.print(f"  • {issue}", style="red")
        console.print("\n[yellow]Run 'python main.py setup' to configure.[/yellow]\n")
        return
    
    db = get_db(config)
    
    console.print("[bold]Starting full pipeline...[/bold]\n", style="cyan")
    start_time = datetime.now()
    
    # Step 1: Scout
    console.print("[bold]━━━ Step 1/5: Scout Agent 🔍 ━━━[/bold]", style="cyan")
    from agents.scout import ScoutAgent
    scout_agent = ScoutAgent(config, db)
    companies_found = scout_agent.run()
    console.print(f"  → Found {companies_found} companies\n")
    
    # Step 2: Hunt
    console.print("[bold]━━━ Step 2/5: Hunter Agent 📧 ━━━[/bold]", style="cyan")
    from agents.hunter import HunterAgent
    hunter_agent = HunterAgent(config, db)
    emails_found = hunter_agent.run()
    console.print(f"  → Extracted emails for {emails_found} companies\n")
    
    # Step 3: Compose
    console.print("[bold]━━━ Step 3/5: Composer Agent ✍️ ━━━[/bold]", style="cyan")
    from agents.composer import ComposerAgent
    composer_agent = ComposerAgent(config, db)
    emails_composed = composer_agent.run()
    console.print(f"  → Composed {emails_composed} personalized emails\n")
    
    # Step 4: Draft
    console.print("[bold]━━━ Step 4/5: Mailer Agent 📬 ━━━[/bold]", style="cyan")
    from agents.mailer import MailerAgent
    mailer_agent = MailerAgent(config, db)
    drafts_created = mailer_agent.create_drafts()
    console.print(f"  → Created {drafts_created} Gmail drafts\n")
    
    # Step 5: Track
    console.print("[bold]━━━ Step 5/5: Tracker Agent 📊 ━━━[/bold]", style="cyan")
    try:
        from agents.tracker import TrackerAgent
        tracker_agent = TrackerAgent(config, db)
        sheet_url = tracker_agent.run()
        console.print(f"  → Google Sheet: {sheet_url}\n")
    except Exception as e:
        console.print(f"  ⚠️  Tracker skipped (Sheets auth needed): {e}\n", style="yellow")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Summary
    console.print(Panel.fit(
        f"[bold green]✅ Pipeline Complete![/bold green]\n\n"
        f"  🔍 Companies discovered: {companies_found}\n"
        f"  📧 Emails extracted: {emails_found}\n"
        f"  ✍️ Emails composed: {emails_composed}\n"
        f"  📬 Gmail drafts created: {drafts_created}\n"
        f"  ⏱️ Total time: {elapsed:.0f} seconds\n\n"
        f"[bold]Next steps:[/bold]\n"
        f"  1. Open Gmail → Drafts to review your emails\n"
        f"  2. Run [bold]python main.py send[/bold] to send approved drafts\n"
        f"  3. Run [bold]python main.py followup[/bold] daily for auto follow-ups",
        title="Summary",
        border_style="green"
    ))


@cli.command()
@click.pass_context
def test(ctx):
    """🧪 Test all API connections."""
    config = ctx.obj['config']
    
    console.print("\n[bold cyan]🧪 Testing API Connections...[/bold cyan]\n")
    
    # Test 1: Ollama
    console.print("[bold]1. Ollama[/bold]")
    try:
        import ollama
        response = ollama.chat(
            model=config.ollama.model,
            messages=[{"role": "user", "content": "Say 'OK' and nothing else."}],
            options={"temperature": 0}
        )
        console.print(f"   ✅ Ollama ({config.ollama.model}): Working — {response['message']['content'].strip()}")
    except Exception as e:
        console.print(f"   ❌ Ollama: {e}", style="red")
    
    # Test 2: Google Places API
    console.print("[bold]2. Google Places API[/bold]")
    if config.google_api_key != "YOUR_GOOGLE_API_KEY":
        try:
            import requests
            resp = requests.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": config.google_api_key,
                    "X-Goog-FieldMask": "places.id,places.displayName"
                },
                json={"textQuery": "IT company in Nairobi", "pageSize": 1}
            )
            if resp.status_code == 200:
                places = resp.json().get("places", [])
                if places:
                    name = places[0].get("displayName", {}).get("text", "unknown")
                    console.print(f"   ✅ Places API: Working — Found '{name}'")
                else:
                    console.print("   ✅ Places API: Connected but no results")
            else:
                console.print(f"   ❌ Places API: HTTP {resp.status_code} — {resp.text[:100]}", style="red")
        except Exception as e:
            console.print(f"   ❌ Places API: {e}", style="red")
    else:
        console.print("   ⚠️  API key not set. Run 'python main.py setup'", style="yellow")
    
    # Test 3: Gmail API
    console.print("[bold]3. Gmail API[/bold]")
    creds_file = config.credentials_dir / "credentials.json"
    if creds_file.exists():
        try:
            from core.gmail_auth import GmailAuth
            auth = GmailAuth(creds_file, config.credentials_dir / "token.json")
            if auth.test_connection():
                console.print("   ✅ Gmail API: Connected and authenticated")
            else:
                console.print("   ❌ Gmail API: Authentication failed", style="red")
        except Exception as e:
            console.print(f"   ❌ Gmail API: {e}", style="red")
    else:
        console.print(f"   ⚠️  credentials.json not found at {creds_file}", style="yellow")
    
    # Test 4: Google Sheets API
    console.print("[bold]4. Google Sheets API[/bold]")
    if creds_file.exists():
        try:
            from core.sheets_auth import SheetsAuth
            auth = SheetsAuth(creds_file, config.credentials_dir / "token_sheets.json")
            if auth.test_connection():
                console.print("   ✅ Sheets API: Connected and authenticated")
            else:
                console.print("   ❌ Sheets API: Authentication failed", style="red")
        except Exception as e:
            console.print(f"   ❌ Sheets API: {e}", style="red")
    else:
        console.print(f"   ⚠️  credentials.json not found at {creds_file}", style="yellow")
    
    # Test 5: CV file
    console.print("[bold]5. CV File[/bold]")
    if CV_PATH.exists():
        size_kb = CV_PATH.stat().st_size / 1024
        console.print(f"   ✅ CV found: {CV_PATH.name} ({size_kb:.0f} KB)")
    else:
        console.print(f"   ⚠️  CV not found at {CV_PATH}", style="yellow")
    
    # Test 6: Database
    console.print("[bold]6. Database[/bold]")
    try:
        db = get_db(config)
        stats = db.get_pipeline_stats()
        total = stats.get(CompanyStatus.DISCOVERED.value, 0)
        console.print(f"   ✅ Database: Working — {total} companies in DB")
    except Exception as e:
        console.print(f"   ❌ Database: {e}", style="red")
    
    console.print("")


if __name__ == "__main__":
    cli()
