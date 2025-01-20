import streamlit as st
from pathlib import Path
from docling.document_converter import DocumentConverter
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from database.snowflake_manager import get_snowflake_session
from config import DATABASE_NAME, SCHEMA_NAME, PDF_DIR, CHUNK_SIZE, CHUNK_OVERLAP
import logging
import requests
import fitz  # PyMuPDF
import io

logger = logging.getLogger(__name__)

def process_and_upload_paper(paper):
    """Process paper and upload to Snowflake."""
    try:
        arxiv_id = paper.entry_id.split('/')[-1]
        converter = DocumentConverter()
        
        # First try HTML to markdown conversion
        try:
            logger.info(f"Converting HTML for paper {arxiv_id}")
            url = f"https://arxiv.org/html/{arxiv_id}"
            result = converter.convert(url)
            md_content = result.document.export_to_markdown()
            chunks = process_markdown_content(md_content, paper)
            logger.info(f"Successfully processed HTML version of paper {arxiv_id}")
        
        except Exception as html_error:
            logger.warning(f"Failed to process HTML, falling back to PDF: {html_error}")
            
            # Fall back to PDF processing
            logger.info(f"Processing PDF for paper {arxiv_id}")
            pdf_path = PDF_DIR / f"{arxiv_id}.pdf"
            paper.download_pdf(filename=str(pdf_path))
            parsed_doc = converter.convert(str(pdf_path))
            md_content = parsed_doc.document.export_to_markdown()
            chunks = process_markdown_content(md_content, paper)
            logger.info(f"Successfully processed PDF version of paper {arxiv_id}")
        
        # Upload to Snowflake
        logger.info(f"Uploading paper {arxiv_id} to Snowflake")
        upload_to_snowflake(paper, chunks)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing paper: {e}")
        st.error(f"Error processing paper: {e}")
        return False

def process_markdown_content(md_content: str, paper):
    """Process markdown content into chunks."""
    # Define headers for splitting
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    
    # Split by headers first
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on, strip_headers=False)
    md_header_splits = markdown_splitter.split_text(md_content)
    
    # Further split into smaller chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )
    
    chunks = text_splitter.split_documents(md_header_splits)
    
    # Add metadata to chunks
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            'paper_id': paper.entry_id.split('/')[-1],
            'chunk_index': i,
            'total_chunks': len(chunks),
            'page_number': 1  # Since HTML doesn't have pages
        })
    
    return chunks

def process_pdf_content(pdf_path: str, paper):
    """Process PDF content into chunks as fallback method."""
    converter = DocumentConverter()
    parsed_doc = converter.convert(pdf_path)
    
    # Convert to markdown
    md_content = parsed_doc.document.export_to_markdown()
    
    # Use the same processing as markdown content
    return process_markdown_content(md_content, paper)

def upload_to_snowflake(paper, chunks):
    """Upload paper and chunks to Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        # Insert paper metadata
        paper_id = paper.entry_id.split('/')[-1]
        
        session.sql("""
            INSERT INTO papers (
                paper_id, title, authors, published_date, 
                abstract, pdf_url, categories
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, params=(
            paper_id,
            paper.title,
            ', '.join(str(author) for author in paper.authors),
            paper.published,
            paper.summary,
            paper.pdf_url,
            ', '.join(paper.categories)
        )).collect()
        
        # Insert chunks
        for chunk in chunks:
            session.sql("""
                INSERT INTO paper_chunks (
                    paper_id, chunk_text, section_header, 
                    chunk_index, page_number
                ) VALUES (?, ?, ?, ?, ?)
            """, params=(
                paper_id,
                chunk.page_content,
                chunk.metadata.get('Header 2', ''),
                chunk.metadata['chunk_index'],
                chunk.metadata['page_number']
            )).collect()
        
    except Exception as e:
        st.error(f"Error uploading to Snowflake: {e}")
        logger.error(f"Error uploading to Snowflake: {e}")
        raise

def display_paper_details(metadata: dict, paper_id: str):
    """Display paper details and PDF viewing options."""
    # Display paper details at the top
    st.markdown(f"### {metadata['title']}")
    st.markdown(f"**Authors:** {metadata['authors']}")
    st.markdown(f"**Published:** {metadata['published_date']}")
    st.markdown(f"**Categories:** {metadata['categories']}")
    
    # Add PDF viewing/download options
    pdf_url = metadata['pdf_url']
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📄 View PDF", use_container_width=True):
            try:
                # Download and display PDF content
                response = requests.get(pdf_url)
                if response.status_code == 200:
                    pdf_content = response.content
                    display_pdf_content(pdf_content)
                else:
                    st.error("Failed to fetch PDF")
            except Exception as e:
                logger.error(f"Error displaying PDF: {e}")
                st.error("Error displaying PDF. Try downloading instead.")
    
    with col2:
        st.markdown(
            f'<a href="{pdf_url}" target="_blank" style="text-decoration: none;">'
            '<div style="border: 1px solid #ddd; padding: 0.5rem; border-radius: 0.3rem; '
            'text-align: center; background-color: #f0f2f6; color: #000000;">'
            '⬇️ Download PDF</div></a>',
            unsafe_allow_html=True
        )
    
    # Display abstract in a scrollable container
    st.markdown("### Abstract")
    st.markdown(
        f"""
        <div style="height: 300px; overflow-y: auto; padding: 1rem; 
                   border: 1px solid #ddd; border-radius: 0.5rem; 
                   background-color: white;">
            {metadata['abstract']}
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Show additional details in expander
    with st.expander("Show arXiv Details"):
        st.markdown(f"**arXiv ID:** {paper_id}")
        st.markdown(f"**PDF URL:** {pdf_url}")

def display_pdf_content(pdf_content: bytes):
    """Display PDF content using PyMuPDF."""
    try:
        # Create a PDF document object
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Create a container for the PDF viewer
        pdf_container = st.container()
        
        # Add page navigation
        total_pages = len(doc)
        page_num = st.slider("Page", 1, total_pages, 1)
        
        # Get the selected page
        page = doc[page_num - 1]
        
        # Convert page to image
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
        img_bytes = pix.tobytes("png")
        
        # Display the page
        with pdf_container:
            st.image(img_bytes, use_column_width=True)
        
        # Close the document
        doc.close()
        
    except Exception as e:
        logger.error(f"Error rendering PDF: {e}")
        st.error("Error rendering PDF page") 