from pathlib import Path
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import snowflake.connector
from typing import List, Dict
import logging
import streamlit as st
from html_to_md import html_to_markdown, save_markdown

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Snowflake configuration
SNOWFLAKE_CONFIG = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"]
}

# Snowflake resource names
WAREHOUSE_NAME = "TEST_PAPERS_WH"
DATABASE_NAME = "TEST_PAPERS_DB"
SCHEMA_NAME = "TEST_PAPERS_SCHEMA"

# Define different chunking configurations
CHUNK_CONFIGS = [
    {"name": "256", "chunk_size": 256, "chunk_overlap": 32},
    {"name": "512", "chunk_size": 512, "chunk_overlap": 64},
    {"name": "1024", "chunk_size": 1024, "chunk_overlap": 128},
]

def initialize_snowflake():
    """Initialize Snowflake resources and create necessary tables for different chunking strategies."""
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()

    try:
        # Create warehouse, database, and schema
        cursor.execute(f"""
            CREATE WAREHOUSE IF NOT EXISTS {WAREHOUSE_NAME}
            WITH WAREHOUSE_SIZE = 'XSMALL'
            AUTO_SUSPEND = 60
            AUTO_RESUME = TRUE;
        """)
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME};")
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {DATABASE_NAME}.{SCHEMA_NAME};")
        
        # Set context
        cursor.execute(f"USE WAREHOUSE {WAREHOUSE_NAME};")
        cursor.execute(f"USE DATABASE {DATABASE_NAME};")
        cursor.execute(f"USE SCHEMA {SCHEMA_NAME};")
        
        # Create tables for each chunking configuration
        for config in CHUNK_CONFIGS:
            table_name = f"TEST_CHUNKS_{config['name']}"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    chunk_id NUMBER IDENTITY PRIMARY KEY,
                    paper_id VARCHAR(255),
                    chunk_text TEXT,
                    section_header VARCHAR(1000),
                    chunk_index INTEGER,
                    page_number INTEGER,
                    chunk_size INTEGER,
                    chunk_overlap INTEGER
                );
            """)
        
        logger.info("Snowflake test chunking tables initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing Snowflake: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def process_arxiv_paper_with_config(md_content: str, paper_id: str, chunk_size: int, chunk_overlap: int) -> List[Dict]:
    """Process arXiv paper content into chunks using specified chunking configuration."""
    try:
        # Define headers for splitting
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        
        # Split by headers first
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on, strip_headers=False)
        md_header_splits = markdown_splitter.split_text(md_content)
        
        # Split into chunks with specified configuration
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        chunks = text_splitter.split_documents(md_header_splits)
        
        # Add metadata to chunks
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                'paper_id': paper_id,
                'chunk_index': i,
                'total_chunks': len(chunks),
                'page_number': 1,  # Since HTML doesn't have pages
                'chunk_size': chunk_size,
                'chunk_overlap': chunk_overlap
            })
        
        return chunks
    
    except Exception as e:
        logger.error(f"Error processing arXiv paper {paper_id}: {e}")
        return []

def upload_chunks_to_snowflake(chunks: List[Dict], config_name: str):
    """Upload chunks to the corresponding Snowflake table."""
    if not chunks:
        return

    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()

    try:
        cursor.execute(f"USE WAREHOUSE {WAREHOUSE_NAME};")
        cursor.execute(f"USE DATABASE {DATABASE_NAME};")
        cursor.execute(f"USE SCHEMA {SCHEMA_NAME};")
        
        table_name = f"TEST_CHUNKS_{config_name}"
        
        # Insert chunks in bulk
        for chunk in chunks:
            cursor.execute(f"""
                INSERT INTO {table_name} (
                    paper_id, chunk_text, section_header, 
                    chunk_index, page_number, chunk_size, chunk_overlap
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                chunk.metadata['paper_id'],
                chunk.page_content,
                chunk.metadata.get('Header 2', ''),
                chunk.metadata['chunk_index'],
                chunk.metadata['page_number'],
                chunk.metadata['chunk_size'],
                chunk.metadata['chunk_overlap']
            ))
        
        conn.commit()
        logger.info(f"Successfully uploaded chunks to {table_name}")
        
    except Exception as e:
        logger.error(f"Error uploading to Snowflake: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    """Main execution function."""
    try:
        # Initialize Snowflake
        initialize_snowflake()
        
        # Process the arXiv paper
        url = "https://arxiv.org/html/2501.09757v1"
        logger.info(f"Processing arXiv paper: {url}")
        
        try:
            # Convert HTML to markdown
            md_content = html_to_markdown(url)
            
            # Save the markdown content
            save_markdown(md_content, url)
            
            # Extract paper ID from URL
            paper_id = url.split('/')[-1]
            
            # Process with each chunking configuration
            for config in CHUNK_CONFIGS:
                chunks = process_arxiv_paper_with_config(
                    md_content,
                    paper_id,
                    config['chunk_size'],
                    config['chunk_overlap']
                )
                
                if chunks:
                    upload_chunks_to_snowflake(chunks, config['name'])
            
            logger.info(f"Completed processing arXiv paper with all configurations")
            
        except Exception as e:
            logger.error(f"Error processing arXiv paper: {e}")
            
    except Exception as e:
        logger.error(f"Error in main execution: {e}")

if __name__ == "__main__":
    main()
