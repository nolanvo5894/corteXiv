import streamlit as st
from snowflake.snowpark import Session
import logging
from config import (
    SNOWFLAKE_CONFIG,
    DATABASE_NAME,
    SCHEMA_NAME
)

logger = logging.getLogger(__name__)

@st.cache_resource
def get_snowflake_session():
    """Get a cached Snowflake session."""
    return Session.builder.configs(SNOWFLAKE_CONFIG).create()

def initialize_snowflake():
    """Initialize Snowflake resources and create necessary tables."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        # Create tables
        _create_papers_table(session)
        _create_chunks_table(session)
        _create_chat_history_table(session)
        _create_paper_summaries_table(session)
        
        logger.info("Successfully initialized Snowflake resources")
        
    except Exception as e:
        st.error(f"Error initializing Snowflake: {e}")
        logger.error(f"Error initializing Snowflake: {e}")
        raise

def _create_papers_table(session):
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {DATABASE_NAME}.{SCHEMA_NAME}.papers (
            paper_id VARCHAR(255) PRIMARY KEY,
            title VARCHAR(1000),
            authors VARCHAR(2000),
            published_date TIMESTAMP,
            abstract TEXT,
            pdf_url VARCHAR(500),
            categories VARCHAR(1000)
        )
    """).collect()

def _create_chunks_table(session):
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {DATABASE_NAME}.{SCHEMA_NAME}.paper_chunks (
            chunk_id NUMBER IDENTITY PRIMARY KEY,
            paper_id VARCHAR(255),
            chunk_text TEXT,
            section_header VARCHAR(1000),
            chunk_index INTEGER,
            page_number INTEGER,
            FOREIGN KEY (paper_id) REFERENCES {DATABASE_NAME}.{SCHEMA_NAME}.papers(paper_id)
        )
    """).collect()

def _create_chat_history_table(session):
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {DATABASE_NAME}.{SCHEMA_NAME}.chat_history (
            chat_id NUMBER IDENTITY PRIMARY KEY,
            paper_id VARCHAR(255),
            timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            role VARCHAR(50),
            content TEXT,
            FOREIGN KEY (paper_id) REFERENCES {DATABASE_NAME}.{SCHEMA_NAME}.papers(paper_id)
        )
    """).collect()

def _create_paper_summaries_table(session):
    """Create table for storing paper summaries."""
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {DATABASE_NAME}.{SCHEMA_NAME}.paper_summaries (
            paper_id VARCHAR(255) PRIMARY KEY,
            summary TEXT,
            generated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            FOREIGN KEY (paper_id) REFERENCES {DATABASE_NAME}.{SCHEMA_NAME}.papers(paper_id)
        )
    """).collect()

def check_paper_exists(paper_id: str) -> bool:
    """Check if paper exists in Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        result = session.sql(
            "SELECT 1 FROM papers WHERE paper_id = ?",
            params=(paper_id,)
        ).collect()
        
        return len(result) > 0
    except Exception as e:
        st.error(f"Error checking paper existence: {e}")
        logger.error(f"Error checking paper existence: {e}")
        raise

def get_saved_papers():
    """Fetch all saved papers from Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        result = session.sql("""
            SELECT 
                paper_id,
                title,
                authors,
                published_date,
                abstract,
                categories,
                pdf_url
            FROM papers
            ORDER BY published_date DESC
        """).collect()
        
        return [
            {
                'paper_id': row[0],
                'title': row[1],
                'authors': row[2],
                'published_date': row[3],
                'abstract': row[4],
                'categories': row[5],
                'pdf_url': row[6]
            }
            for row in result
        ]
    except Exception as e:
        st.error(f"Error fetching saved papers: {e}")
        logger.error(f"Error fetching saved papers: {e}")
        raise

def get_paper_summary(paper_id: str) -> str:
    """Fetch existing paper summary from Snowflake."""
    session = get_snowflake_session()
    try:
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        result = session.sql("""
            SELECT summary FROM paper_summaries WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        return result[0][0] if result else None
    except Exception as e:
        logger.error(f"Error fetching paper summary: {e}")
        raise

def save_paper_summary(paper_id: str, summary: str):
    """Save paper summary to Snowflake."""
    session = get_snowflake_session()
    try:
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        session.sql("""
            INSERT INTO paper_summaries (paper_id, summary)
            VALUES (?, ?)
        """, params=(paper_id, summary)).collect()
    except Exception as e:
        logger.error(f"Error saving paper summary: {e}")
        raise

def delete_paper(paper_id: str) -> bool:
    """Delete a paper and all its related data from Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {DATABASE_NAME}").collect()
        session.sql(f"USE SCHEMA {SCHEMA_NAME}").collect()
        
        # Delete in reverse order of dependencies
        # First delete chat history
        session.sql("""
            DELETE FROM chat_history 
            WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        # Delete paper summaries
        session.sql("""
            DELETE FROM paper_summaries 
            WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        # Delete paper chunks
        session.sql("""
            DELETE FROM paper_chunks 
            WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        # Finally delete the paper
        session.sql("""
            DELETE FROM papers 
            WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        return True
        
    except Exception as e:
        logger.error(f"Error deleting paper {paper_id}: {e}")
        return False 