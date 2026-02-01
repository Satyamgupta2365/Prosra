import asyncio
import json
import re
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from urllib.parse import urlparse, urljoin
import os
import requests

from playwright.async_api import async_playwright, Page, Browser
from groq import Groq

# Rich TUI Imports
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.syntax import Syntax
from rich.live import Live
from rich.prompt import Prompt
from rich import box

console = Console()

class EnhancedCompanyResearchScraper:
    """
    Advanced multi-source company research scraper with deep AI analysis
    Combines web scraping, news collection, review aggregation, and competitive intelligence
    """
    
    # Groq API Key — read from environment or passed in
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    
    def __init__(self, company_name: str, groq_api_key: str = None, log_callback: Callable[[str], None] = None):
        self.company_name = company_name
        self.groq_api_key = groq_api_key or self.GROQ_API_KEY
        self.client = Groq(api_key=self.groq_api_key)
        self.log = log_callback or print
        self.data = {
            'company_name': company_name,
            'timestamp': datetime.now().isoformat(),
            'website_data': {},
            'news_articles': [],
            'reviews': [],
            'social_mentions': [],
            'competitors': [],
            'pricing_tiers': [],
            'features': [],
            'blog_posts': []
        }
    
    async def search_company_website(self, page: Page) -> Optional[str]:
        """Find company's official website using Google search"""
        try:
            search_query = f"{self.company_name} official website"
            await page.goto(f"https://www.google.com/search?q={search_query}", wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            urls = await page.evaluate('''() => {
                const results = Array.from(document.querySelectorAll('a[href]'));
                return results
                    .map(a => a.href)
                    .filter(href => href.includes('http') && !href.includes('google'))
                    .slice(0, 5);
            }''')
            
            if urls:
                for url in urls:
                    if self.company_name.lower().replace(' ', '') in url.lower():
                        return url
                return urls[0]
            
            return f"https://www.{self.company_name.lower().replace(' ', '')}.com"
        except Exception as e:
            self.log(f"[red]❌ Error finding website: {str(e)}[/]")
            return None
    
    async def scrape_page_content(self, page: Page, url: str, page_name: str) -> Dict[str, Any]:
        """Scrape comprehensive content from a single page"""
        try:
            self.log(f"   📄 Scraping [cyan]{page_name}[/]...")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)
            
            page_data = await page.evaluate('''() => {
                return {
                    title: document.title,
                    text: document.body.innerText,
                    headings: Array.from(document.querySelectorAll('h1, h2, h3'))
                        .map(h => ({level: h.tagName, text: h.innerText.trim()})),
                    links: Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({text: a.innerText.trim(), href: a.href}))
                        .filter(l => l.text && l.href),
                    meta_description: document.querySelector('meta[name="description"]')?.content || '',
                    meta_keywords: document.querySelector('meta[name="keywords"]')?.content || ''
                };
            }''')
            
            return {
                'url': url,
                'page_name': page_name,
                'scraped': True,
                'title': page_data['title'],
                'content': page_data['text'][:8000],
                'headings': page_data['headings'][:20],
                'links': page_data['links'][:50],
                'meta': {
                    'description': page_data['meta_description'],
                    'keywords': page_data['meta_keywords']
                }
            }
        except Exception as e:
            self.log(f"[red]   ❌ Failed to scrape {page_name}: {str(e)}[/]")
            return {'url': url, 'page_name': page_name, 'scraped': False, 'error': str(e)}
    
    async def discover_important_pages(self, page: Page, base_url: str) -> Dict[str, str]:
        """Discover important pages on the website"""
        try:
            await page.goto(base_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)
            
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({
                        text: a.innerText.trim().toLowerCase(),
                        href: a.href
                    }))
                    .filter(l => l.text && l.href);
            }''')
            
            page_mapping = {
                'homepage': base_url,
                'about': None,
                'pricing': None,
                'features': None,
                'products': None,
                'blog': None,
                'team': None,
                'contact': None,
                'testimonials': None,
                'documentation': None
            }
            
            keywords = {
                'about': ['about', 'about us', 'company', 'who we are'],
                'pricing': ['pricing', 'plans', 'price', 'cost'],
                'features': ['features', 'capabilities', 'product'],
                'products': ['products', 'solutions'],
                'blog': ['blog', 'news', 'articles', 'insights'],
                'team': ['team', 'people', 'leadership'],
                'contact': ['contact', 'get in touch', 'reach us'],
                'testimonials': ['testimonials', 'reviews', 'customers', 'case studies'],
                'documentation': ['docs', 'documentation', 'guides', 'help']
            }
            
            for link in links:
                for page_type, page_keywords in keywords.items():
                    if page_mapping[page_type] is None:
                        if any(kw in link['text'] or kw in link['href'].lower() for kw in page_keywords):
                            page_mapping[page_type] = link['href']
            
            return {k: v for k, v in page_mapping.items() if v}
        except Exception as e:
            self.log(f"[yellow]   ⚠️  Error discovering pages: {str(e)}[/]")
            return {'homepage': base_url}
    
    def extract_pricing_tiers(self, content: str) -> List[Dict]:
        """Extract pricing information from content"""
        pricing_tiers = []
        price_pattern = r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:\/|per)?\s*(month|year|mo|yr|annually|monthly)?'
        plan_patterns = ['free', 'basic', 'starter', 'pro', 'professional', 'premium', 'enterprise', 'business', 'team', 'individual']
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            for plan in plan_patterns:
                if plan in line_lower and len(line.strip()) < 200:
                    context = '\n'.join(lines[max(0, i-3):min(len(lines), i+8)])
                    price_matches = re.findall(price_pattern, context, re.IGNORECASE)
                    
                    if price_matches or 'free' in line_lower:
                        tier = {
                            'name': plan.capitalize(),
                            'price': f"${price_matches[0][0]}" if price_matches else ('Free' if 'free' in line_lower else 'Contact Sales'),
                            'billing_period': price_matches[0][1] if price_matches and price_matches[0][1] else 'month',
                            'description': line.strip()[:200]
                        }
                        pricing_tiers.append(tier)
        
        seen = set()
        unique_tiers = []
        for tier in pricing_tiers:
            tier_key = (tier['name'].lower(), tier['price'])
            if tier_key not in seen:
                seen.add(tier_key)
                unique_tiers.append(tier)
        
        return unique_tiers
    
    def extract_features(self, content: str, headings: List[Dict]) -> List[Dict]:
        """Extract product features from content"""
        features = []
        feature_indicators = ['feature', 'capability', 'benefit', 'includes', 'what you get', 'key features']
        
        lines = content.split('\n')
        in_feature_section = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            line_stripped = line.strip()
            
            if any(indicator in line_lower for indicator in feature_indicators):
                in_feature_section = True
                continue
            
            if in_feature_section:
                if (line_stripped.startswith(('•', '-', '*', '✓', '→')) or 
                    re.match(r'^\d+[\.\)]\s', line_stripped)):
                    
                    feature_text = re.sub(r'^[•\-*✓→\d\.\)]\s*', '', line_stripped)
                    if 10 < len(feature_text) < 300:
                        features.append({
                            'name': feature_text[:100],
                            'description': feature_text
                        })
                
                if line_stripped and line_stripped.isupper() and len(line_stripped) > 3:
                    in_feature_section = False
        
        return features[:25]
    
    async def search_news_articles(self, page: Page) -> List[Dict]:
        """Search for news articles about the company"""
        articles = []
        try:
            self.log("   📰 Searching news articles...")
            search_query = f"{self.company_name} news"
            await page.goto(f"https://www.google.com/search?q={search_query}&tbm=nws", wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            news_data = await page.evaluate('''() => {
                const items = Array.from(document.querySelectorAll('div.SoaBEf, div.n0jPhd'));
                return items.slice(0, 10).map(item => {
                    const titleEl = item.querySelector('[role="heading"], h3');
                    const linkEl = item.querySelector('a');
                    const sourceEl = item.querySelector('.NUnG9d, .CEMjEf');
                    const dateEl = item.querySelector('.OSrXXb, .WG9SHc');
                    
                    return {
                        title: titleEl?.innerText || '',
                        url: linkEl?.href || '',
                        source: sourceEl?.innerText || 'Unknown',
                        date: dateEl?.innerText || ''
                    };
                }).filter(item => item.title && item.url);
            }''')
            
            articles.extend(news_data)
        except Exception as e:
            self.log(f"[yellow]   ⚠️  Error searching news: {str(e)}[/]")
        
        return articles
    
    async def search_reviews(self, page: Page) -> List[Dict]:
        """Search for company reviews on various platforms"""
        reviews = []
        try:
            self.log("   ⭐ Searching reviews...")
            platforms = ['G2', 'Trustpilot', 'Capterra', 'Product Hunt']
            
            for platform in platforms:
                search_query = f"{self.company_name} {platform} reviews"
                await page.goto(f"https://www.google.com/search?q={search_query}", wait_until='networkidle')
                await page.wait_for_timeout(1500)
                
                snippets = await page.evaluate('''() => {
                    const results = Array.from(document.querySelectorAll('.VwiC3b, .s3v9rd'));
                    return results.slice(0, 2).map(el => el.innerText).filter(t => t);
                }''')
                
                for snippet in snippets:
                    if snippet:
                        reviews.append({
                            'platform': platform,
                            'snippet': snippet[:500],
                            'collected_date': datetime.now().strftime('%Y-%m-%d')
                        })
        except Exception as e:
            self.log(f"[yellow]   ⚠️  Error searching reviews: {str(e)}[/]")
        
        return reviews
    
    async def search_social_mentions(self, page: Page) -> List[Dict]:
        """Search for social media mentions"""
        mentions = []
        try:
            self.log("   💬 Searching social mentions...")
            platforms = [
                ('LinkedIn', 'site:linkedin.com/company'),
                ('Twitter', 'site:twitter.com OR site:x.com'),
                ('Reddit', 'site:reddit.com')
            ]
            
            for platform_name, site_filter in platforms:
                search_query = f"{self.company_name} {site_filter}"
                await page.goto(f"https://www.google.com/search?q={search_query}", wait_until='networkidle')
                await page.wait_for_timeout(1500)
                
                results = await page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('.g'));
                    return items.slice(0, 3).map(item => {
                        const link = item.querySelector('a');
                        const snippet = item.querySelector('.VwiC3b, .s3v9rd');
                        return {
                            url: link?.href || '',
                            snippet: snippet?.innerText || ''
                        };
                    }).filter(r => r.url && r.snippet);
                }''')
                
                for result in results:
                    mentions.append({
                        'platform': platform_name,
                        'url': result['url'],
                        'snippet': result['snippet'][:300]
                    })
        except Exception as e:
            self.log(f"[yellow]   ⚠️  Error searching social: {str(e)}[/]")
        
        return mentions
    
    async def search_competitors(self, page: Page) -> List[Dict]:
        """Search for competitors"""
        competitors = []
        try:
            self.log("   🎯 Searching competitors...")
            queries = [
                f"{self.company_name} competitors",
                f"{self.company_name} alternatives",
                f"companies like {self.company_name}"
            ]
            
            for query in queries:
                await page.goto(f"https://www.google.com/search?q={query}", wait_until='networkidle')
                await page.wait_for_timeout(1500)
                
                text = await page.evaluate('() => document.body.innerText')
                
                words = text.split()
                for i, word in enumerate(words):
                    if word.lower() in ['vs', 'versus', 'alternative', 'competitor', 'vs.']:
                        if i + 1 < len(words):
                            potential = words[i + 1].strip('.,;:()[]{}')
                            if potential.istitle() and 2 < len(potential) < 30:
                                competitors.append({'name': potential, 'source': query})
        except Exception as e:
            self.log(f"[yellow]   ⚠️  Error searching competitors: {str(e)}[/]")
        
        seen = set()
        unique_competitors = []
        for comp in competitors:
            if comp['name'] not in seen:
                seen.add(comp['name'])
                unique_competitors.append(comp)
        
        return unique_competitors[:15]
    
    async def deep_ai_analysis(self, all_data: Dict) -> Dict:
        """Perform comprehensive AI analysis using Llama 3.3"""
        self.log("\n[bold purple]🤖 Performing Deep AI Analysis...[/]")
        
        try:
            prompt = f"""You are an expert business intelligence analyst. Analyze the following comprehensive data about {self.company_name} and provide a detailed strategic report.

=== COLLECTED DATA ===

WEBSITE DATA:
{json.dumps(all_data['website_data'], indent=2)[:3000]}

PRICING INFORMATION:
{json.dumps(all_data['pricing_tiers'], indent=2)}

FEATURES IDENTIFIED:
{json.dumps(all_data['features'], indent=2)[:2000]}

NEWS ARTICLES ({len(all_data['news_articles'])} found):
{json.dumps(all_data['news_articles'], indent=2)[:2000]}

REVIEWS ({len(all_data['reviews'])} found):
{json.dumps(all_data['reviews'], indent=2)[:1500]}

SOCIAL MENTIONS ({len(all_data['social_mentions'])} found):
{json.dumps(all_data['social_mentions'], indent=2)[:1500]}

COMPETITORS IDENTIFIED ({len(all_data['competitors'])} found):
{json.dumps(all_data['competitors'], indent=2)}

=== ANALYSIS REQUIRED ===

Provide a comprehensive analysis in the following JSON structure:

{{
  "company_overview": {{
    "description": "what the company does in 2-3 sentences",
    "industry": "primary industry/sector",
    "target_market": "who their customers are",
    "value_proposition": "their unique value proposition",
    "business_model": "how they make money"
  }},
  "product_analysis": {{
    "core_products": ["list of main products/services"],
    "key_features": ["top 5-7 most important features"],
    "technology_stack": "technologies they appear to use",
    "product_maturity": "early-stage/growth/mature",
    "innovation_level": "low/medium/high"
  }},
  "pricing_strategy": {{
    "pricing_model": "freemium/subscription/enterprise/etc",
    "price_range": "estimated price range",
    "pricing_positioning": "budget/mid-market/premium/enterprise",
    "monetization_approach": "how they monetize",
    "estimated_arpu": "estimated average revenue per user if possible"
  }},
  "market_position": {{
    "market_strength": "weak/moderate/strong/dominant",
    "brand_reputation": "analysis of brand perception",
    "market_share_estimate": "estimated market position",
    "growth_trajectory": "declining/stable/growing/rapid growth",
    "competitive_advantages": ["list key advantages"]
  }},
  "competitive_landscape": {{
    "main_competitors": ["top 3-5 competitors"],
    "competitive_threats": ["key threats"],
    "differentiation_factors": ["how they differ from competition"],
    "market_gaps": ["opportunities they're not addressing"]
  }},
  "customer_sentiment": {{
    "overall_sentiment": "positive/neutral/negative/mixed",
    "common_praise_points": ["what customers love"],
    "common_complaints": ["what customers complain about"],
    "review_summary": "summary of customer feedback",
    "nps_estimate": "estimated net promoter score if possible"
  }},
  "content_marketing": {{
    "content_quality": "poor/fair/good/excellent",
    "content_frequency": "how often they publish",
    "thought_leadership": "are they industry thought leaders?",
    "seo_presence": "their search visibility"
  }},
  "strengths_weaknesses": {{
    "top_5_strengths": ["their biggest strengths"],
    "top_5_weaknesses": ["their main weaknesses"],
    "opportunities": ["market opportunities"],
    "threats": ["external threats"]
  }},
  "strategic_insights": {{
    "growth_potential": "assessment of growth potential",
    "investment_worthiness": "if this seems like a good investment",
    "partnership_potential": "potential for partnerships",
    "acquisition_target": "could they be acquired? by whom?"
  }},
  "actionable_recommendations": [
    "specific recommendation 1",
    "specific recommendation 2",
    "specific recommendation 3"
  ],
  "executive_summary": "A comprehensive 4-6 paragraph executive summary covering all key findings, insights, and recommendations.",
  "risk_score": {{
    "overall_score": "0-100 numerical score",
    "risk_factors": ["key risk factors"],
    "confidence_level": "how confident in this analysis"
  }}
}}

IMPORTANT: Respond with ONLY valid JSON. No markdown formatting, no code blocks, no explanations. Just pure JSON."""

            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a senior business intelligence analyst with 20 years of experience. Provide detailed, actionable analysis in JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=4000,
            )
            
            response_text = completion.choices[0].message.content.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            analysis = json.loads(response_text)
            
            self.log("[green]✅ AI Analysis Complete![/]")
            return analysis
            
        except Exception as e:
            self.log(f"[red]❌ AI Analysis Error: {str(e)}[/]")
            return {
                "error": f"AI analysis failed: {str(e)}",
                "basic_summary": f"Collected {len(all_data.get('features', []))} features, {len(all_data.get('pricing_tiers', []))} pricing tiers, {len(all_data.get('news_articles', []))} news articles"
            }
    
    async def run_complete_research(self) -> Dict:
        """Execute complete research pipeline"""
        self.log(f"\n[bold]🚀 STARTING COMPREHENSIVE RESEARCH[/]")
        self.log(f"[bold]📊 Company/Product: [cyan]{self.company_name}[/][/]")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            self.log("[bold]🔍 PHASE 1: Website Discovery & Scraping[/]")
            website_url = await self.search_company_website(page)
            
            if website_url:
                self.log(f"[green]✅ Found website: {website_url}[/]")
                important_pages = await self.discover_important_pages(page, website_url)
                self.log(f"[green]✅ Discovered {len(important_pages)} important pages[/]")
                
                for page_name, url in important_pages.items():
                    page_data = await self.scrape_page_content(page, url, page_name)
                    self.data['website_data'][page_name] = page_data
                    
                    if page_data.get('scraped'):
                        content = page_data.get('content', '')
                        headings = page_data.get('headings', [])
                        
                        self.data['pricing_tiers'].extend(self.extract_pricing_tiers(content))
                        self.data['features'].extend(self.extract_features(content, headings))
            
            self.log(f"\n[bold]📰 PHASE 2: News & Media Collection[/]")
            self.data['news_articles'] = await self.search_news_articles(page)
            self.log(f"[green]✅ Collected {len(self.data['news_articles'])} news articles[/]")
            
            self.log(f"\n[bold]⭐ PHASE 3: Review Aggregation[/]")
            self.data['reviews'] = await self.search_reviews(page)
            self.log(f"[green]✅ Collected {len(self.data['reviews'])} review snippets[/]")
            
            self.log(f"\n[bold]💬 PHASE 4: Social Media Analysis[/]")
            self.data['social_mentions'] = await self.search_social_mentions(page)
            self.log(f"[green]✅ Collected {len(self.data['social_mentions'])} social mentions[/]")
            
            self.log(f"\n[bold]🎯 PHASE 5: Competitive Intelligence[/]")
            self.data['competitors'] = await self.search_competitors(page)
            self.log(f"[green]✅ Identified {len(self.data['competitors'])} potential competitors[/]")
            
            await browser.close()
        
        analysis = await self.deep_ai_analysis(self.data)
        
        final_output = {
            'metadata': {
                'research_date': datetime.now().isoformat(),
                'company_name': self.company_name,
                'scraper_version': '2.0',
                'analysis_model': 'llama-3.3-70b-versatile'
            },
            'raw_data': self.data,
            'ai_deep_analysis': analysis,
            'metrics': {
                'pages_scraped': len([p for p in self.data['website_data'].values() if p.get('scraped')]),
                'pricing_tiers_found': len(self.data['pricing_tiers']),
                'features_identified': len(self.data['features']),
                'news_articles': len(self.data['news_articles']),
                'reviews_collected': len(self.data['reviews']),
                'social_mentions': len(self.data['social_mentions']),
                'competitors_identified': len(self.data['competitors'])
            }
        }
        
        return final_output
    
    def save_to_json(self, output: Dict, filename: str = None):
        """Save research to JSON file"""
        if filename is None:
            filename = f"{self.company_name.replace(' ', '_')}_comprehensive_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n[bold green]💾 Full JSON saved to: {filename}[/]")
        return filename
    
    def save_analysis_text(self, output: Dict, filename: str = None):
        """Save executive summary and analysis to readable text file"""
        if filename is None:
            filename = f"{self.company_name.replace(' ', '_')}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        analysis = output.get('ai_deep_analysis', {})
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"COMPREHENSIVE RESEARCH REPORT: {self.company_name}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
            
            f.write("EXECUTIVE SUMMARY\n")
            f.write("-"*80 + "\n")
            exec_summary = analysis.get('executive_summary', 'No summary available')
            if isinstance(exec_summary, dict):
                exec_summary = json.dumps(exec_summary, indent=2)
            elif isinstance(exec_summary, list):
                exec_summary = '\n'.join(str(item) for item in exec_summary)
            else:
                exec_summary = str(exec_summary)
            f.write(exec_summary + "\n\n")
            
            if analysis.get('company_overview'):
                f.write("\nCOMPANY OVERVIEW\n")
                f.write("-"*80 + "\n")
                for key, value in analysis['company_overview'].items():
                    f.write(f"{key.replace('_', ' ').title()}: {value}\n")
            
            if analysis.get('product_analysis'):
                f.write("\n\nPRODUCT ANALYSIS\n")
                f.write("-"*80 + "\n")
                for key, value in analysis['product_analysis'].items():
                    f.write(f"{key.replace('_', ' ').title()}: {value}\n")
            
            if analysis.get('market_position'):
                f.write("\n\nMARKET POSITION\n")
                f.write("-"*80 + "\n")
                for key, value in analysis['market_position'].items():
                    f.write(f"{key.replace('_', ' ').title()}: {value}\n")
            
            if analysis.get('strengths_weaknesses'):
                f.write("\n\nSTRENGTHS & WEAKNESSES (SWOT)\n")
                f.write("-"*80 + "\n")
                for key, value in analysis['strengths_weaknesses'].items():
                    f.write(f"\n{key.replace('_', ' ').title()}:\n")
                    if isinstance(value, list):
                        for item in value:
                            f.write(f"  • {item}\n")
                    else:
                        f.write(f"  {value}\n")
            
            if analysis.get('actionable_recommendations'):
                f.write("\n\nACTIONABLE RECOMMENDATIONS\n")
                f.write("-"*80 + "\n")
                recs = analysis['actionable_recommendations']
                if isinstance(recs, list):
                    for i, rec in enumerate(recs, 1):
                        f.write(f"{i}. {rec}\n")
                else:
                    f.write(f"{recs}\n")
            
            f.write("\n\nRESEARCH METRICS\n")
            f.write("-"*80 + "\n")
            for key, value in output.get('metrics', {}).items():
                f.write(f"{key.replace('_', ' ').title()}: {value}\n")
        
        self.log(f"[bold green]📄 Analysis text saved to: {filename}[/]")
        return filename


class GeneralTopicResearchScraper(EnhancedCompanyResearchScraper):
    """
    Scraper specialized for deep research on general topics (e.g., "RAG Techniques", "Quantum Computing")
    Scrapes multiple sources to provide a comprehensive overview.
    """
    
    async def search_relevant_websites(self, page: Page) -> List[Dict]:
        """Find top 3 relevant websites for the topic"""
        try:
            self.log(f"   🔍 Searching for authoritative sources on: [cyan]{self.company_name}[/]...")
            # 'self.company_name' here acts as the 'topic'
            search_query = f"{self.company_name} detailed guide overview"
            await page.goto(f"https://www.google.com/search?q={search_query}", wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # Extract organic results
            results = await page.evaluate('''() => {
                const results = Array.from(document.querySelectorAll('.g'));
                return results.map(item => {
                    const link = item.querySelector('a');
                    const title = item.querySelector('h3');
                    const snippet = item.querySelector('.VwiC3b, .s3v9rd');
                    return {
                        url: link?.href,
                        title: title?.innerText,
                        snippet: snippet?.innerText
                    };
                })
                .filter(r => r.url && r.title && !r.url.includes('google') && !r.url.includes('youtube'))
                .slice(0, 3);
            }''')
            
            return results
        except Exception as e:
            self.log(f"[red]❌ Error finding sources: {str(e)}[/]")
            return []

    async def deep_ai_analysis(self, all_data: Dict) -> Dict:
        """Perform comprehensive AI analysis for a general topic"""
        self.log("\n[bold purple]🤖 Performing Deep Topic Analysis...[/]")
        
        try:
            prompt = f"""You are an expert research analyst. Analyze the following scraped data about the topic "{self.company_name}" and provide a deep technical and strategic report.

=== COLLECTED DATA ===

WEBSITE CONTENT:
{json.dumps(all_data['website_data'], indent=2)[:8000]}

NEWS/RECENT UPDATES:
{json.dumps(all_data['news_articles'], indent=2)[:3000]}

SOCIAL DISCUSSIONS:
{json.dumps(all_data['social_mentions'], indent=2)[:2000]}

=== ANALYSIS REQUIRED ===

Provide a comprehensive research report in the following JSON structure:

{{
  "topic_overview": {{
    "definition": "Clear, concise definition of the topic",
    "key_concepts": ["List of core concepts/terminologies"],
    "importance": "Why this topic matters now",
    "history_context": "Brief background/evolution"
  }},
  "technical_deep_dive": {{
    "how_it_works": "Detailed technical explanation",
    "core_components": ["List of main components/parts"],
    "technologies_involved": "Related technologies/stacks",
    "architecture": "Description of typical architecture/structure"
  }},
  "state_of_the_art": {{
    "current_trends": ["List of current trends"],
    "recent_advancements": ["Major recent breakthroughs"],
    "leading_players": ["Companies/Labs leading this field"],
    "adoption_level": "Experimental/Early Adopters/Mainstream"
  }},
  "pros_cons_challenges": {{
    "advantages": ["Key benefits"],
    "disadvantages": ["Drawbacks/Limitations"],
    "implementation_challenges": ["Difficulties in adopting/using it"]
  }},
  "use_cases_applications": [
    {{
      "sector": "Industry or Field",
      "application": "Specific application example",
      "impact": "The impact it creates"
    }}
  ],
  "future_outlook": {{
    "predictions": ["1-3 year predictions"],
    "research_directions": "Where research is heading",
    "disruption_potential": "High/Medium/Low and why"
  }},
  "executive_summary": "A comprehensive 4-6 paragraph executive summary covering all key insights.",
  "learning_resources": [
    "Suggested topics to learn next",
    "Prerequisite knowledge needed"
  ]
}}

IMPORTANT: Respond with ONLY valid JSON. No markdown."""

            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a senior research scientist. Provide detailed, accurate analysis in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000,
            )
            
            response_text = completion.choices[0].message.content.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            return json.loads(response_text)
            
        except Exception as e:
            self.log(f"[red]❌ AI Analysis Error: {str(e)}[/]")
            return {"error": str(e), "executive_summary": "Analysis failing."}

    async def run_complete_research(self) -> Dict:
        """Execute general topic research pipeline"""
        self.log(f"\n[bold]🚀 STARTING GENERAL TOPIC RESEARCH[/]")
        self.log(f"[bold]📚 Topic: [cyan]{self.company_name}[/][/]")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = await context.new_page()
            
            # Phase 1: Search Sources
            self.log("[bold]🔍 PHASE 1: Source Discovery & Scraping[/]")
            sources = await self.search_relevant_websites(page)
            
            if sources:
                self.log(f"[green]✅ Found {len(sources)} key sources[/]")
                
                for i, source in enumerate(sources):
                    self.log(f"   Reading source {i+1}: {source['title']}")
                    # Reuse existing scrape_page_content
                    page_data = await self.scrape_page_content(page, source['url'], f"Source_{i+1}")
                    self.data['website_data'][f"source_{i+1}"] = page_data
            else:
                self.log("[red]❌ No sources found. Trying fallback scrape of wiki...[/]")
            
            # Phase 2: News/Updates
            self.log(f"\n[bold]📰 PHASE 2: Latest News/Developments[/]")
            self.data['news_articles'] = await self.search_news_articles(page)
            
            # Phase 3: Social Sentiment (useful for tech trends)
            self.log(f"\n[bold]💬 PHASE 3: Community Discussions[/]")
            self.data['social_mentions'] = await self.search_social_mentions(page)
            
            await browser.close()
        
        # Phase 4: Analysis
        analysis = await self.deep_ai_analysis(self.data)
        
        return {
            'metadata': {
                'research_date': datetime.now().isoformat(),
                'topic': self.company_name,
                'scraper_type': 'General_Topic',
                'model': 'llama-3.3-70b-versatile'
            },
            'raw_data': self.data,
            'ai_deep_analysis': analysis,
            'metrics': {
                'sources_analyzed': len(self.data['website_data']),
                'news_found': len(self.data['news_articles']),
                'social_mentions': len(self.data['social_mentions'])
            }
        }


class NotionMCPIntegration:
    """Handles Notion MCP integration for automated page creation"""
    
    DEFAULT_DATABASE_ID = "2c1fa1336f4d80c285c1c5a5d0a4c42a"
    # Notion token should come from environment or be passed in at runtime
    DEFAULT_NOTION_TOKEN = None
    
    def __init__(self, database_id: str = None, notion_token: str = None):
        self.database_id = database_id or self.DEFAULT_DATABASE_ID
        # Prefer explicit token, then environment variable; avoid hardcoding secrets
        self.notion_token = notion_token or os.environ.get("NOTION_TOKEN", "")
        self.notion_api_url = "https://api.notion.com/v1/pages" 
        self.headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    def create_notion_page(self, research_output: Dict) -> bool:
        """Create a Notion page with research results"""
        try:
            analysis = research_output.get('ai_deep_analysis', {})
            company_name = research_output['metadata']['company_name']
            
            page_data = {
                "parent": {"database_id": self.database_id},
                "properties": {
                    "Name": {
                        "title": [
                            {
                                "text": {
                                    "content": f"{company_name} - Research Report"
                                }
                            }
                        ]
                    }
                },
                "children": [
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [{"type": "text", "text": {"content": f"Research Report: {company_name}"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": str(analysis.get('executive_summary') or 'No summary available')[:2000]}}]
                        }
                    }
                ]
            }
            
            response = requests.post(
                self.notion_api_url,
                headers=self.headers,
                json=page_data
            )
            
            if response.status_code == 200:
                print(f"✅ Notion page created successfully!")
                return True
            else:
                print(f"❌ Failed to create Notion page: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Notion integration error: {str(e)}")
            return False

# ----------------- TUI Implementation -----------------

class TUIState:
    WELCOME = "welcome"
    PROCESSING = "processing"
    RESULTS = "results"

class TUIApp:
    def __init__(self):
        self.state = TUIState.WELCOME
        self.company_name = ""
        self.logs = []
        self.results = None
        self.notion_created = False
        self.files = {}

    def get_header(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        title = Text("🧠 Enhanced Company Researcher", style="bold cyan")
        subtitle = Text("Automated Analysis & Strategic Intelligence", style="italic white")
        
        status = Text(self.company_name if self.company_name else "Ready", style="italic green")
        
        grid.add_row(Text(" v2.0 ", style="reverse bold"), title, status)
        grid.add_row("", subtitle, "")
        
        return Panel(grid, style="white on black", box=box.HEAVY_HEAD)

    def get_footer(self) -> Panel:
        text = Text()
        if self.state == TUIState.RESULTS:
            text.append("[Q] Quit ", style="bold red")
            text.append("[V] View Full Analysis ", style="bold blue")
            text.append("[C] Chat with AI ", style="bold magenta")
            text.append("[N] Create Notion Page ", style="bold green")
        else:
            text.append("[Ctrl+C] Quit ", style="bold red")
        
        return Panel(Align.center(text), style="white on black", box=box.HEAVY_HEAD)

    def get_welcome_content(self) -> Panel:
        content = Table.grid(expand=True, padding=(1, 2))
        content.add_column(justify="center", ratio=1)
        
        title = Text("ENHANCED COMPANY RESEARCHER", style="bold cyan size=20")
        
        desc = Text("""
This tool uses advanced AI and web scraping to:
• Scrape data from multiple sources
• Gather news, reviews, and social mentions
• Analyze competitors or deeply research topics
• Generate strategic reports with Llama 3
""", justify="center", style="yellow")

        content.add_row(title)
        content.add_row("")
        content.add_row(desc)
        content.add_row("")
        content.add_row(Text("Press Enter to Start...", style="blink white"))
        
        return Panel(content, border_style="cyan", padding=(2, 2))

    def get_step_panel(self, title: str, content, style: str, border_style: str) -> Panel:
        """Create a section that looks like a 'Step' from the reference image"""
        return Panel(
            content,
            title=f"[bold {style} on black] {title} [/]",
            title_align="left",
            border_style=border_style,
            box=box.SQUARE,
            padding=(0, 1)
        )

    def render_layout(self, content=None):
        # We ignore the 'content' arg usually passed for simple layouts and build a full dashboard
        layout = Layout()
        
        # Structure: Header -> Main Stack -> Footer
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="stack"),
            Layout(name="footer", size=1)
        )
        
        # 1. HEADER (Blue Theme)
        # We create a big blocky title using simple characters since we don't have figlet
        title_text = Text("ANTIGRAVITY RESEARCHER", style="bold white on blue", justify="center")
        layout["header"].update(Panel(title_text, style="on blue", box=box.HEAVY))

        # 2. STACK (The "Steps")
        # We will split the stack based on what we have
        
        stack_elements = []
        
        # Step A: Configuration / Info (Always visible or at top)
        if self.company_name:
            info_text = f"Target: {self.company_name}\nMode: {'Topic Research' if isinstance(scraper, GeneralTopicResearchScraper) else 'Company Analysis'}"
            stack_elements.append(
                self.get_step_panel("1. CONFIGURATION", Text(info_text, style="cyan"), "cyan", "cyan")
            )

        # Step B: Live Logs (The "Active" process)
        # Just show last 5-6 logs to keep it compact if we have other things, or full if processing
        log_height = 10 if self.state == TUIState.PROCESSING else 6
        log_text = "\n".join(self.logs[-log_height:])
        stack_elements.append(
             self.get_step_panel("2. LIVE EXECUTION LOGS", Text(log_text, style="white"), "green", "green")
        )

        # Step C: Results (Only if results exist)
        if self.results:
            # Create a nice grid for metrics
            metrics = self.results.get("metrics", {})
            m_grid = Table.grid(expand=True, padding=(0, 2))
            m_grid.add_column(style="bold yellow")
            m_grid.add_column(style="white")
            m_grid.add_column(style="bold yellow")
            m_grid.add_column(style="white")
            
            m_items = list(metrics.items())
            half = len(m_items) // 2
            for i in range(half):
                k1, v1 = m_items[i]
                if i + half < len(m_items):
                    k2, v2 = m_items[i+half]
                    m_grid.add_row(k1.replace('_', ' ').title(), str(v1), k2.replace('_', ' ').title(), str(v2))
                else:
                    m_grid.add_row(k1.replace('_', ' ').title(), str(v1), "", "")
            
            stack_elements.append(
                self.get_step_panel("3. ANALYSIS METRICS", m_grid, "yellow", "yellow")
            )
            
            # Step D: Executive Summary Preview
            analysis = self.results.get('ai_deep_analysis', {})
            summary = str(analysis.get('executive_summary') or "No summary available")
            summary_preview = summary[:300] + "..."
            stack_elements.append(
                self.get_step_panel("4. EXECUTIVE SUMMARY", Text(summary_preview, style="dim white"), "magenta", "magenta")
            )

        # Render the stack elements
        # We need to split the 'stack' layout dynamically
        if stack_elements:
            splits = [Layout(ratio=1) for _ in range(len(stack_elements))]
            layout["stack"].split_column(*splits)
            for i, element in enumerate(stack_elements):
                layout["stack"].children[i].update(element)
        else:
            layout["stack"].update(Panel("Waiting to start...", border_style="dim"))

        # 3. FOOTER (Status Line)
        # Matches the bottom bar in image
        if self.state == TUIState.RESULTS:
            keys = "[Q] Quit | [V] View Full Info | [C] Chat AI | [N] Notion"
            bg = "red"
        elif self.state == TUIState.PROCESSING:
            keys = "PROCESSING... PLEASE WAIT"
            bg = "yellow"
        else:
            keys = "[Enter] Start"
            bg = "blue"
            
        layout["footer"].update(Text(f" {keys} ", style=f"bold white on {bg}", justify="left"))
        
        return layout

    async def chat_session(self):
        """Interactive chat session with the analyzed data"""
        if not self.results:
            return

        # Simple separate loop for chat to maximize screen space for text
        console.clear()
        
        # Initialize Groq client
        client = Groq(api_key=EnhancedCompanyResearchScraper.GROQ_API_KEY)
        
        # Context
        analysis = self.results.get('ai_deep_analysis', {})
        context = json.dumps(analysis, indent=2)
        
        messages = [
            {
                "role": "system",
                "content": f"You are an expert analyst. Data context:\n{context}\nAnswer strictly based on this."
            }
        ]
        
        # Print header
        console.print(Panel("💬 CHAT MODE (Type 'exit' to return)", style="bold white on purple"))
        
        while True:
            user_input = Prompt.ask("\n[bold green]You[/]")
            if user_input.lower() in ['exit', 'back', 'quit']:
                break
                
            messages.append({"role": "user", "content": user_input})
            
            with console.status("[bold purple]AI is thinking...[/]"):
                try:
                    completion = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                    )
                    response = completion.choices[0].message.content
                    console.print(Panel(response, title="AI Analyst", border_style="purple"))
                    messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]")

    def view_full_analysis(self):
        if not self.results:
             return
        
        analysis = self.results.get('ai_deep_analysis', {})
        text = json.dumps(analysis, indent=2)
        console.pager(text)

# Make scraper global for TUI access to type
scraper = None

async def main():
    global scraper
    app = TUIApp()
    
    # 1. Welcome & Config
    console.clear()
    console.print(Panel.fit(
        "[1] 🏢 Company/Product Analysis\n[2] 📚 General Topic Research",
        title="ANTIGRAVITY RESEARCHER", 
        subtitle="Select Mode",
        style="bold white on blue"
    ))
    mode_choice = Prompt.ask("Select Mode", choices=["1", "2"], default="1")
    
    term_label = "Company/Product Name" if mode_choice == "1" else "Research Topic"
    app.company_name = Prompt.ask(f"[bold cyan]Enter {term_label}[/]")
    
    # Instantiate Scraper
    if mode_choice == "1":
        scraper = EnhancedCompanyResearchScraper(app.company_name, log_callback=lambda msg: app.logs.append(msg))
    else:
        scraper = GeneralTopicResearchScraper(app.company_name, log_callback=lambda msg: app.logs.append(msg))
    
    scraper.log = lambda msg: app.logs.append(msg)

    # 2. Processing Loop
    app.state = TUIState.PROCESSING
    
    # We use a finer-grained refresh loop to allow the 'log' callback to update the UI smoothly
    # without needing 'Live' to wrap everything awkwardly
    
    with Live(app.render_layout(), refresh_per_second=4, screen=True) as live:
        # Define a wrapper for logging that also updates the live display
        def update_display(msg):
            app.logs.append(msg)
            live.update(app.render_layout())
        
        scraper.log = update_display
        
        try:
            results = await scraper.run_complete_research()
            app.results = results
            
            update_display("\n[bold]💾 Saving Results...[/]")
            app.files['json'] = scraper.save_to_json(results)
            app.files['text'] = scraper.save_analysis_text(results)
            
            # Transition to Results State
            app.state = TUIState.RESULTS
            live.update(app.render_layout())
            
            # We exit the Live context here to allow 'input' (Prompt) to work in the main loop
            # Otherwise Prompt fights with Live display
            await asyncio.sleep(1)
            
        except Exception as e:
            app.logs.append(f"[bold red]CRITICAL ERROR: {str(e)}[/]")
            live.update(app.render_layout())
            await asyncio.sleep(5)
            return

    # 3. Interactive Results Loop
    # Now that processing is done, we redraw the layout and ask for input
    while True:
        console.clear()
        console.print(app.render_layout())
        
        choice = Prompt.ask("Action", choices=["q", "v", "n", "c"], default="c")
        
        if choice == "q":
            break
        elif choice == "v":
            app.view_full_analysis()
        elif choice == "c":
            await app.chat_session()
        elif choice == "n":
            with console.status("[bold green]Creating Notion Page...[/]"):
                notion = NotionMCPIntegration()
                success = notion.create_notion_page(app.results)
                app.notion_created = success
                if success:
                    console.print("[green]Page created![/]")
                    await asyncio.sleep(1)

    console.print("\n[bold cyan]Thank you for using Enhanced Company Researcher![/]")

if __name__ == "__main__":
    asyncio.run(main())