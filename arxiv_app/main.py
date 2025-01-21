import streamlit as st
# Set page config must be the first Streamlit command
st.set_page_config(layout="wide")

from services.arxiv_service import search_arxiv_papers, paper_to_dict
from services.chat_service import create_chat_interface
from database.snowflake_manager import (
    initialize_snowflake, 
    check_paper_exists, 
    get_saved_papers,
    get_snowflake_session,
    delete_paper
)
from models.paper import CachedSearch
from utils.logging_config import setup_logging
from services.pdf_service import process_and_upload_paper
import arxiv
import pandas as pd
from snowflake.core import Root
from snowflake.cortex import Complete
from config import (
    CORTEX_SEARCH_DATABASE, 
    CORTEX_SEARCH_SCHEMA, 
    CORTEX_SEARCH_SERVICE,
    CORTEX_SEARCH_ABSTRACT_SERVICE
)
from functools import partial

logger = setup_logging()
logger.info("Starting main.py")

try:
    from services.chat_service import create_chat_interface
    logger.info("Successfully imported chat_service")
except Exception as e:
    logger.error(f"Error importing chat_service: {e}")
    raise

def initialize_session_state():
    """Initialize all session state variables."""
    defaults = {
        "page": "search",
        "search_query": "",
        "sort_by": "Relevance",
        "max_results": 100,
        "current_page": 1,
        "cached_results": None,
        "search_clicked": False,
        "previous_page": "search",
        "last_nav_selection": None
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

@st.cache_data(ttl=3600)
def get_cached_search(query: str, max_results: int) -> CachedSearch:
    """Get cached search results or perform new search."""
    logger.info(f"Searching with query: {query}, max_results: {max_results}")
    
    # Perform search
    papers = search_arxiv_papers(
        query,
        max_results=max_results
    )
    
    if papers:
        # Convert to DataFrame while preserving order
        papers_df = pd.DataFrame([paper_to_dict(paper, idx) for idx, paper in enumerate(papers)])
        papers_df = papers_df.sort_values('sort_idx').drop('sort_idx', axis=1)
        
        # Create cached result
        return CachedSearch(
            query=query,
            max_results=max_results,
            papers=papers,
            papers_df=papers_df
        )
    return None

def main():
    """Main application function."""
    initialize_session_state()
    handle_navigation()
    
    if st.session_state.page == "chat":
        logger.info(f"Displaying chat for paper {st.session_state.current_paper_id}")
        create_chat_interface(st.session_state.current_paper_id)
        if st.button("← Back"):
            st.session_state.page = st.session_state.previous_page
            st.rerun()
    elif st.session_state.page == "library":
        display_library_page()
    elif st.session_state.page == "search":
        display_search_page()
    elif st.session_state.page == "how_to":
        display_how_to_page()

def display_library_page():
    """Display the personal library page."""
    st.title("Personal Library")
    
    try:
        papers = get_saved_papers()
        
        if not papers:
            st.info("Your library is empty. Add papers from the Search page!")
            return

        # Create tabs for different search methods
        search_tab, semantic_tab = st.tabs(["Metadata Search", "Semantic Search"])
        
        # Initialize filtered_papers with all papers
        if 'filtered_papers' not in st.session_state:
            st.session_state.filtered_papers = papers
        
        # Handle metadata search
        with search_tab:
            # Add search input
            search_term = st.text_input(
                "What do you want to search for in your library?",
                value=st.session_state.get('metadata_search_term', ''),
                placeholder="Enter your search term...",
                key="metadata_search"
            ).lower()
            
            # Add field selector
            search_field = st.selectbox(
                "Search in",
                options=["All Fields", "Title", "Authors", "Categories"],
                index=0,
                key="metadata_field"
            )
            
            # Add buttons under the filter bar
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔍 Search", use_container_width=True):
                    # Store search term in session state
                    st.session_state.metadata_search_term = search_term
                    
                    # Filter papers based on selected field and search term
                    if search_term:
                        if search_field == "All Fields":
                            st.session_state.filtered_papers = [
                                p for p in papers
                                if search_term in p['title'].lower()
                                or search_term in p['authors'].lower()
                                or search_term in p['categories'].lower()
                            ]
                        elif search_field == "Title":
                            st.session_state.filtered_papers = [p for p in papers if search_term in p['title'].lower()]
                        elif search_field == "Authors":
                            st.session_state.filtered_papers = [p for p in papers if search_term in p['authors'].lower()]
                        elif search_field == "Categories":
                            st.session_state.filtered_papers = [p for p in papers if search_term in p['categories'].lower()]
            
            with col2:
                if st.button("🌬️ Clear", use_container_width=True):
                    # Reset search state
                    st.session_state.filtered_papers = papers
                    st.session_state.metadata_search_term = ""
                    st.rerun()

        # Handle semantic search
        with semantic_tab:
            semantic_query = st.text_input(
                "Search paper abstracts semantically",
                value=st.session_state.get('semantic_search_term', ''),
                placeholder="Describe what you're looking for...",
                key="semantic_search"
            )
            
            # Add buttons under the search bar
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔍 Search", key="semantic_search_btn", use_container_width=True):
                    if semantic_query:
                        # Store search term in session state
                        st.session_state.semantic_search_term = semantic_query
                        
                        # Get Snowflake session and setup Cortex search
                        session = get_snowflake_session()
                        root = Root(session)
                        svc = root.databases[CORTEX_SEARCH_DATABASE].schemas[CORTEX_SEARCH_SCHEMA].cortex_search_services[CORTEX_SEARCH_ABSTRACT_SERVICE]
                        
                        # Perform semantic search
                        response = svc.search(
                            semantic_query, 
                            ["ABSTRACT", "PAPER_ID"], 
                            limit=len(papers)
                        )
                        
                        # Map results back to full paper metadata
                        paper_id_to_metadata = {p['paper_id']: p for p in papers}
                        st.session_state.filtered_papers = [
                            paper_id_to_metadata[result['PAPER_ID']]
                            for result in response.results
                            if result['PAPER_ID'] in paper_id_to_metadata
                        ]
            
            with col2:
                if st.button("🌬️ Clear", key="semantic_clear_btn", use_container_width=True):
                    # Reset search state
                    st.session_state.filtered_papers = papers
                    st.session_state.semantic_search_term = ""
                    st.rerun()

        # Display number of results
        st.write(f"Found {len(st.session_state.filtered_papers)} papers")
        
        # Display papers in a single column layout
        for idx, paper in enumerate(st.session_state.filtered_papers):
            with st.container(border=True):
                st.markdown(f"### {paper['title']}")
                st.write(f"**Authors:** {paper['authors']}")
                st.write(f"**Published:** {paper['published_date'].strftime('%Y-%m-%d')}")
                st.write(f"**Categories:** {paper['categories']}")
                
                # Add buttons for actions
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Chat with Paper", key=f"lib_chat_{paper['paper_id']}"):
                        st.session_state.previous_page = "library"
                        st.session_state.current_paper_id = paper['paper_id']
                        st.session_state.page = "chat"
                        st.rerun()
                with col2:
                    st.markdown(f"[Download PDF]({paper['pdf_url']})")
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{paper['paper_id']}", 
                               type="secondary", use_container_width=True):
                        with st.spinner('Deleting paper...'):
                            if delete_paper(paper['paper_id']):
                                st.success(f"Deleted paper: {paper['title']}")
                                st.rerun()
                            else:
                                st.error("Failed to delete paper")
                
                # Show abstract in expander
                with st.expander("Show Abstract"):
                    st.write(paper['abstract'])
            
            st.markdown("---")  # Add separator between papers
                
    except Exception as e:
        st.error(f"Error loading library: {str(e)}")
        logger.error(f"Error loading library: {e}")

def display_search_page():
    """Display the search page."""
    st.title("❄️ CorteXiv ❄️")
    st.markdown("## 🌬️ A Cooler arXiv Experience")
    st.markdown("##### 🧐 Search for Papers and Chat with Your Own Personal arXiv Librarian")
    
    # Add some space after the headers
    st.markdown("---")
    
    # Initialize Snowflake only once at app startup
    if 'db_initialized' not in st.session_state:
        with st.spinner('Initializing database...'):
            initialize_snowflake()
            st.session_state.db_initialized = True
    
    if display_search_form() or (st.session_state.search_clicked and st.session_state.search_query):
        if (st.session_state.cached_results is None or 
            st.session_state.search_query != st.session_state.cached_results.query or
            st.session_state.max_results != st.session_state.cached_results.max_results):
            
            with st.spinner('Searching arXiv...'):
                st.session_state.cached_results = get_cached_search(
                    st.session_state.search_query,
                    st.session_state.max_results
                )
        
        if st.session_state.cached_results:
            display_search_results()
        else:
            st.warning("No papers found matching your search criteria.")

def display_search_form():
    """Display and handle the search form."""
    with st.form(key="search_form"):
        prev_query = st.session_state.get('search_query', '')
        prev_max_results = st.session_state.get('max_results', 100)
        
        search_query = st.text_input(
            "What do you want to learn about today?",
            value=prev_query,
            placeholder="Example: 'quantum computing' OR 'machine learning'",
            key="search_input"
        )
        
        max_results = st.slider(
            "Maximum number of results",
            min_value=10, max_value=1000,
            value=prev_max_results,
            step=10,
            key="max_results_slider"
        )

        # Add info about sorting
        st.info("Results are sorted by relevance and then by date (newest first)")

        if st.form_submit_button("Search"):
            st.session_state.update({
                'search_query': search_query,
                'max_results': max_results,
                'search_clicked': True,
                'current_page': 1
            })
            return True
    return False

@st.fragment
def display_paper_container(paper, paper_obj, idx, papers):
    """Fragment to display a single paper container."""
    with st.expander(f"{idx + 1}. {paper['Title']}"):
        st.write(f"**Authors:** {paper['Authors']}")
        st.write(f"**Published:** {paper['Published']}")
        st.write(f"**Categories:** {paper['Categories']}")
        st.write("**Abstract:**")
        st.write(paper['Abstract'])
        st.write(f"**arXiv ID:** {paper['arXiv ID']}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown(f"[Download PDF]({paper['PDF URL']})")
        
        with col2:
            paper_id = paper['arXiv ID']
            if check_paper_exists(paper_id):
                if st.button("Chat with Paper", key=f"chat_{paper_id}"):
                    st.session_state.previous_page = "search"
                    st.session_state.current_paper_id = paper_id
                    st.session_state.page = "chat"
                    st.rerun()
            else:
                if st.button(f"Add to Database", key=f"add_{paper_id}"):
                    with st.spinner('Processing paper...'):
                        success = process_and_upload_paper(paper_obj)
                        if success:
                            st.success(f"Added paper: {paper['Title']}")
                            st.rerun()
                        else:
                            st.error("Failed to add paper")

def display_search_results():
    """Display paginated search results."""
    papers = st.session_state.cached_results.papers
    papers_df = st.session_state.cached_results.papers_df
    
    papers_per_page = 10
    total_pages = len(papers_df) // papers_per_page + (1 if len(papers_df) % papers_per_page > 0 else 0)
    
    st.write(f"Found {len(papers_df)} papers")
    
    page = st.selectbox(
        "Page",
        options=range(1, total_pages + 1),
        index=st.session_state.current_page - 1,
        format_func=lambda x: f"Page {x} of {total_pages}"
    )
    
    if page != st.session_state.current_page:
        st.session_state.current_page = page

    start_idx = (page - 1) * papers_per_page
    end_idx = min(start_idx + papers_per_page, len(papers_df))
    
    cols = st.columns(2)
    for idx in range(start_idx, end_idx):
        with cols[idx % 2]:
            paper = papers_df.iloc[idx]
            paper_obj = papers[idx]
            display_paper_container(paper, paper_obj, idx, papers)

def handle_navigation():
    """Handle navigation between pages."""
    st.sidebar.title("Pages")
    
    current_nav_index = 0  # Default to Search
    if st.session_state.page == "library":
        current_nav_index = 1
    elif st.session_state.page == "how_to":
        current_nav_index = 2
    elif st.session_state.page == "chat":
        current_nav_index = 0 if st.session_state.previous_page == "search" else 1
    
    nav_selection = st.sidebar.radio(
        "Go to",
        ["🔍 Search Papers", "🔖 Personal Library", "❓ How to Use"],
        index=current_nav_index,
        key="nav_radio"
    )
    
    # Handle navigation changes when selection changes
    if nav_selection != st.session_state.get("last_nav_selection"):
        st.session_state.last_nav_selection = nav_selection
        
        if nav_selection == "🔍 Search Papers":
            st.session_state.page = "search"
            st.rerun()
        elif nav_selection == "🔖 Personal Library":
            st.session_state.page = "library"
            st.rerun()
        elif nav_selection == "❓ How to Use":
            st.session_state.page = "how_to"
            st.rerun()

def display_how_to_page():
    """Display the How to Use guide."""
    st.title("❄️ Welcome to CorteXiv! ❄️")
    
    st.markdown("""
    ## 🎯 Here's How to Use This:
    
    ### 🔍 Search Like a Pro
    * Type what interests you (e.g., "quantum computing", "AI ethics")
    * We'll fetch the most relevant papers and sort them by date
    * No more endless scrolling through irrelevant stuff!
    
    ### 🔖 Build Your Library
    * Found something cool? Hit "Add to Database"
    * Your papers are safely stored in your Personal Library
    * Access them anytime, anywhere!
    
    ### 🧐 Chat with Your Papers
    * Click "Chat with Paper" to start a conversation
    * Ask questions, get summaries, explore ideas
    * We'll suggest deep dive questions to help you explore
    * Pick up your conversations anytime - we remember everything!
    * It's like having a super-smart research assistant!
    
    ### 🌟 Pro Tips:
    * Use the semantic search in your library to find papers by concept
    * Combine keywords with 'OR' for broader searches
    * Chat feature works best with specific questions
    
    ### 🎉 Ready to Start?
    Head over to the Search Papers page and dive into the world of research!
    
    *Powered by Snowflake Cortex and Mistral LLM* ✨
    """)

if __name__ == "__main__":
    main() 