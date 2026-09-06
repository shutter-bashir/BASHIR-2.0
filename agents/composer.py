import json
import logging
from pathlib import Path

import ollama
from rich.console import Console

from core.models import Company, ContactEmail, EmailDraft, CompanyStatus
from core.database import Database
from config import Config, load_config

console = Console()

class ComposerAgent:
    """Agent responsible for composing personalized email drafts using Ollama."""
    
    def __init__(self, config: Config, database: Database):
        """Initialize the Composer Agent."""
        self.config = config
        self.db = database
        self.template = self._load_template('email_prompt.txt')
        self.followup_template = self._load_template('followup_prompt.txt')
        
    def run(self, limit: int = 0) -> int:
        """Compose emails for all companies with emails but no drafts. Returns count composed."""
        companies_with_emails = self.db.get_companies_without_drafts()
        if limit > 0:
            companies_with_emails = companies_with_emails[:limit]
            
        count = 0
        for company, contact_email in companies_with_emails:
            draft = self.compose_initial_email(company, contact_email)
            if draft:
                self.db.add_draft(draft)
                count += 1
                console.print(f"[green]✍️ Composed email for {company.name}[/green]")
                
        return count

    def compose_initial_email(self, company: Company, email: ContactEmail) -> EmailDraft:
        """Generate a personalized initial outreach email."""
        from datetime import datetime
        profile = self.config.student
        
        prompt = self.template.format(
            company_name=company.name,
            company_category=", ".join(company.types[:3]) if company.types else "IT",
            company_address=company.address or "Nairobi, Kenya",
            student_name=profile.name,
            student_email=profile.email,
            course=profile.course,
            university=profile.university,
            year=profile.year,
            skills=", ".join(profile.skills),
            interests=", ".join(profile.interests),
            attachment_start=profile.attachment_start,
            attachment_end=profile.attachment_end,
            attachment_duration=profile.attachment_duration
        ) if self.template else f"Write an application email for {profile.name} to {company.name}."
        
        response = self._call_ollama(prompt)
        if not response:
            response = self._get_fallback_email(company)
            
        # The template now includes the complete sign-off, so we don't append one here
        body = response.get('body', '')
        
        return EmailDraft(
            company_id=company.id,
            to_email=email.email,
            subject=response.get('subject', 'Industrial Attachment Application'),
            body=body,
            status=CompanyStatus.EMAIL_COMPOSED.value,
            created_at=datetime.now()
        )

    def compose_followup_email(self, original_draft: EmailDraft, company: Company, followup_number: int) -> dict:
        """Generate a follow-up email referencing the original."""
        prompt = self.followup_template.format(
            student_name=self.config.student.name,
            university=self.config.student.university,
            course=self.config.student.course,
            student_email=self.config.student.email,
            company_name=company.name,
            original_subject=original_draft.subject,
            original_sent_date=original_draft.sent_at.strftime('%Y-%m-%d') if original_draft.sent_at else 'recently',
            followup_number=followup_number,
            max_followups=self.config.email.max_followups
        ) if self.followup_template else f"Write a professional follow-up #{followup_number} email to {company.name}."
        
        response = self._call_ollama(prompt)
        if not response:
            response = {
                "subject": f"Re: {original_draft.subject}",
                "body": f"Dear Hiring Manager,\n\nI am following up on my previous email regarding an industrial attachment opportunity at {company.name}. I remain very interested and would appreciate any updates.\n\nThank you for your time."
            }
            
        # The template now includes the complete sign-off, so we don't append one here
        body = response.get('body', '')
        
        return {
            "subject": response.get('subject', f"Re: {original_draft.subject}"),
            "body": body
        }

    def _call_ollama(self, prompt: str) -> dict:
        """Call Ollama API and parse JSON response."""
        try:
            response = ollama.chat(
                model=self.config.ollama.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a professional email writer for a university student seeking industrial attachment. Always return valid JSON with 'subject' and 'body' fields."
                    },
                    {"role": "user", "content": prompt}
                ],
                format="json",
                options={
                    "temperature": self.config.ollama.temperature, 
                    "top_p": getattr(self.config.ollama, 'top_p', 0.9)
                }
            )
            return json.loads(response["message"]["content"])
        except Exception as e:
            logging.warning(f"Ollama failed: {e}. Using fallback template.")
            return None

    def _get_fallback_email(self, company: Company) -> dict:
        """Return a well-crafted template email when Ollama fails."""
        profile = self.config.student
        skills_str = ", ".join(profile.skills[:5]) if profile.skills else "Python, SQL, Git"
        
        return {
            "subject": f"Industrial Attachment Application - {profile.course} Student, {profile.university}",
            "body": f"""Dear Hiring Manager,

I am writing to express my strong interest in a {profile.attachment_duration} industrial attachment at {company.name}, starting in {profile.attachment_start}. I am a year-{profile.year} {profile.course} student at {profile.university}, and I am eager to contribute to your technology and IT departments.

I have practical experience with {skills_str}, and I am passionate about applying my skills in a real-world environment. I am a fast learner who thrives on solving technical challenges.

My CV is attached for your review. I welcome the opportunity to discuss how my technical skills and enthusiasm can contribute to your team.

Thank you for your time and consideration.

Sincerely,

{profile.name}"""
        }

    def _load_template(self, filename: str) -> str:
        """Load a prompt template from the templates directory."""
        from config import TEMPLATES_DIR
        template_path = TEMPLATES_DIR / filename
        try:
            if template_path.exists():
                return template_path.read_text(encoding='utf-8')
            return ""
        except Exception as e:
            logging.error(f"Failed to load template {filename}: {e}")
            return ""
