import arxiv
import logging
import streamlit as st
from typing import List
import pandas as pd

logger = logging.getLogger(__name__)

def search_arxiv_papers(query: str, max_results: int = 100, sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance) -> list:
    """Search arXiv papers based on user query."""
    logger.info(f"Starting search for query: {query} with max_results: {max_results}, sort_by: {sort_by}")
    
    client = arxiv.Client(
        page_size=100,
        delay_seconds=0,
        num_retries=3
    )
    
    # Always use Relevance for initial search
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
        sort_order=arxiv.SortOrder.Descending
    )
    
    try:
        logger.info("Executing arXiv search...")
        papers = list(client.results(search))
        # Sort papers by published date after fetching
        papers.sort(key=lambda x: x.published, reverse=True)
        logger.info(f"Found {len(papers)} papers")
        return papers
    except Exception as e:
        logger.error(f"Error in search_arxiv_papers: {str(e)}")
        logger.exception("Full traceback:")
        st.error(f"Error fetching papers: {str(e)}")
        return []

def paper_to_dict(paper: arxiv.Result, sort_idx: int) -> dict:
    """Convert arxiv paper to dictionary format."""
    return {
        'sort_idx': sort_idx,
        'Title': paper.title,
        'Authors': ', '.join(str(author) for author in paper.authors),
        'Published': paper.published.strftime('%Y-%m-%d'),
        'Categories': ', '.join(paper.categories),
        'Abstract': paper.summary,
        'PDF URL': paper.pdf_url,
        'arXiv ID': paper.entry_id.split('/')[-1]
    } 