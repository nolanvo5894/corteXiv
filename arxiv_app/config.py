import streamlit as st
from pathlib import Path

# Snowflake configuration
SNOWFLAKE_CONFIG = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"]
}

# Snowflake resource names
WAREHOUSE_NAME = "ARXIV_PAPERS_WH"
DATABASE_NAME = "ARXIV_PAPERS_DB"
SCHEMA_NAME = "ARXIV_PAPERS_SCHEMA"

# Cortex configuration
CORTEX_SEARCH_DATABASE = "ARXIV_PAPERS_DB"
CORTEX_SEARCH_SCHEMA = "ARXIV_PAPERS_SCHEMA"
CORTEX_SEARCH_SERVICE = "ARXIV_SEARCH_SERVICE_CHUNKS_CS"
CORTEX_SEARCH_ABSTRACT_SERVICE = "ARXIV_SEARCH_SERVICE_ABSTRACTS_CS"

COLUMNS = ["CHUNK_TEXT", "PAPER_ID"]

# Local storage settings
PDF_DIR = Path("artifacts/papers")
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Add these chunking configurations
NUM_CHUNKS = 5
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128