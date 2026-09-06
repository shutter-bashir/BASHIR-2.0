import asyncio
import aiohttp
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from core.models import Company, ContactEmail, CompanyStatus
from core.database import Database
from config import Config, load_config

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')  
IGNORED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.zip'}
IGNORED_EMAILS = {
    'example@example.com', 'email@example.com', 'noreply@', 'no-reply@', 
    'mailer-daemon@', 'sentry', 'wixpress', 'example.com', 'domain.com', 'company.com'
}
CONTACT_SUBPAGES = ['', '/contact', '/contact-us', '/about', '/about-us', '/careers', '/team', '/info']

class HunterAgent:
    """Hunter Agent extracts email addresses from company websites."""
    
    def __init__(self, config: Config, database: Database):
        self.config = config
        self.db = database
        self.max_concurrent = 5
        self.timeout = 8
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def run(self, limit: int = 0) -> int:
        """Run email extraction for all companies without emails. Returns emails found count."""
        # Note: adjust this method call depending on core.database implementation
        companies = self.db.get_companies_without_emails() 
        if limit > 0:
            companies = companies[:limit]
            
        if not companies:
            logger.info("No companies found that need email extraction.")
            return 0
            
        return asyncio.run(self._extract_all(companies, limit))

    async def _extract_all(self, companies: list[Company], limit: int) -> int:
        """Extract emails from all companies concurrently."""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        total_emails = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Extracting emails...", total=len(companies))
            
            async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
                tasks = [self._extract_from_company_wrapped(company, session, semaphore, progress, task_id) for company in companies]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for res in results:
                    if isinstance(res, list):
                        for email in res:
                            self.db.add_email(email)
                            total_emails += 1
                    elif isinstance(res, Exception):
                        logger.debug(f"Task exception: {res}")
                        
        logger.info(f"Hunter complete. Processed {len(companies)} companies, found {total_emails} emails.")
        return total_emails

    async def _extract_from_company_wrapped(self, company: Company, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, progress, task_id) -> list[ContactEmail]:
        try:
            return await self._extract_from_company(company, session, semaphore)
        finally:
            progress.advance(task_id)

    async def _extract_from_company(self, company: Company, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore) -> list[ContactEmail]:
        """Extract emails from a single company's website."""
        from datetime import datetime
        emails_found = []
        
        async with semaphore:
            if company.website:
                found_emails = await self._crawl_website(company.website, session)
                if found_emails:
                    for email_addr, source, confidence in found_emails:
                        if self._is_valid_email(email_addr):
                            emails_found.append(ContactEmail(
                                company_id=company.id,
                                email=email_addr,
                                source_url=source,
                                confidence=confidence,
                                discovered_at=datetime.now()
                            ))
            
            if not emails_found and company.website:
                guessed = self._guess_email_patterns(company)
                for email_addr, confidence in guessed:
                    if self._is_valid_email(email_addr):
                        emails_found.append(ContactEmail(
                            company_id=company.id,
                            email=email_addr,
                            source_url="pattern_guess",
                            confidence=confidence,
                            discovered_at=datetime.now()
                        ))
                        
        return emails_found

    async def _crawl_website(self, base_url: str, session: aiohttp.ClientSession) -> set[tuple[str, str, float]]:
        """Crawl a website's contact pages for emails. Returns set of (email, source_url, confidence)."""
        results = set()
        parsed_base = urlparse(base_url)
        if not parsed_base.scheme:
            base_url = "https://" + base_url
            
        for subpage in CONTACT_SUBPAGES:
            url = urljoin(base_url, subpage)
            try:
                async with session.get(url, ssl=False) as response:
                    if response.status == 200:
                        text = await response.text()
                        soup = BeautifulSoup(text, 'html.parser')
                        
                        import urllib.parse
                        # mailto links
                        for a in soup.find_all('a', href=True):
                            href = a.get('href', '')
                            if href.lower().startswith('mailto:'):
                                raw_email = href[7:].split('?')[0].strip()
                                email = urllib.parse.unquote(raw_email).strip()
                                if email:
                                    results.add((email, url, 0.95))
                                    
                        # Regex matches
                        confidence = 0.85 if 'contact' in subpage.lower() else 0.70
                        for match in EMAIL_REGEX.finditer(text):
                            email = urllib.parse.unquote(match.group().strip()).strip()
                            results.add((email, url, confidence))
                            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(f"Failed to fetch {url}: {e}")
                
        return results

    def _guess_email_patterns(self, company: Company) -> list[tuple[str, float]]:
        """Generate common email patterns from domain. Returns list of (email, confidence)."""
        if not company.website:
            return []
            
        domain = urlparse(company.website).netloc
        if domain.startswith('www.'):
            domain = domain[4:]
            
        if not domain:
            return []
            
        prefixes = ['info', 'hello', 'hr', 'careers', 'admin', 'contact']
        return [(f"{prefix}@{domain}", 0.40) for prefix in prefixes]

    def _is_valid_email(self, email: str) -> bool:
        """Validate email is not a false positive."""
        email_lower = email.lower()
        if len(email) > 254:
            return False
            
        for ext in IGNORED_EXTENSIONS:
            if email_lower.endswith(ext):
                return False
                
        for ignored in IGNORED_EMAILS:
            if ignored in email_lower:
                return False
                
        return True
