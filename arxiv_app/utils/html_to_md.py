import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import re
from pathlib import Path

def html_to_markdown(url):
    """Convert arXiv HTML paper to Markdown format."""
    # Fetch HTML content
    response = requests.get(url)
    response.raise_for_status()
    
    # Convert HTML to Markdown
    markdown_content = md(response.text, heading_style="ATX")
    
    return markdown_content

def save_markdown(content, url):
    """Save markdown content to a file."""
    # Extract paper ID from URL and use it as filename
    paper_id = re.search(r'abs/([0-9.]+)', url)
    if paper_id:
        filename = f"arxiv_{paper_id.group(1)}.md"
    else:
        filename = "arxiv_paper.md"
    
    # Save to file
    Path(filename).write_text(content, encoding='utf-8')
    print(f"Markdown file saved as: {filename}") 