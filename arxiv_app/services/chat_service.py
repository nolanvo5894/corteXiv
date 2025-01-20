import streamlit as st
from snowflake.core import Root
from snowflake.cortex import Complete
from database.snowflake_manager import get_snowflake_session
from config import (
    CORTEX_SEARCH_DATABASE, 
    CORTEX_SEARCH_SCHEMA, 
    CORTEX_SEARCH_SERVICE,
    DATABASE_NAME,
    SCHEMA_NAME,
    NUM_CHUNKS,
    COLUMNS
)
import json
import re
import logging
from .pdf_service import display_paper_details  # Add this import

logger = logging.getLogger(__name__)

def create_chat_interface(paper_id: str):
    """Create a chat interface for a specific paper."""
    st.title(f"Chat with Paper")
    
    # Get paper metadata
    metadata = get_paper_metadata(paper_id)
    if metadata:
        # Show compact paper info at the top
        st.markdown(f"### {metadata['title']}")
        
        # Paper details expander
        with st.expander("Show Paper Details"):
            st.markdown(f"**Authors:** {metadata['authors']}")
            st.markdown(f"**Published:** {metadata['published_date']}")
            st.markdown(f"**Categories:** {metadata['categories']}")
            st.markdown(f"[Open PDF]({metadata['pdf_url']})")
        
        # Key Insights section with button
        with st.expander("📌 Key Insights", expanded=False):
            summary = get_paper_summary(paper_id)
            if not summary:
                if st.button("Generate Key Insights"):
                    with st.spinner("Generating paper insights..."):
                        summary = generate_paper_summary(paper_id, metadata)
                        save_paper_summary(paper_id, summary)
                        st.rerun()  # Refresh to show the generated summary
            
            if summary:
                st.markdown(
                    f"""
                    <div style="
                        padding: 1rem;
                        border-radius: 0.5rem;
                        border: 1px solid #404040;
                        font-size: 0.95rem;
                        line-height: 1.5;
                    ">
                        {summary}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        
        st.markdown("---")
        
        # Chat interface
        # Clear messages if we're switching to a different paper
        if "current_chat_paper_id" not in st.session_state or st.session_state.current_chat_paper_id != paper_id:
            st.session_state.messages = []
            st.session_state.current_chat_paper_id = paper_id
            
            # Add system message with paper context
            system_msg = f"""You are an AI assistant helping to discuss a research paper.
Paper Details:
- Title: {metadata['title']}
- Authors: {metadata['authors']}
- Published: {metadata['published_date']}
- Categories: {metadata['categories']}
- Abstract: {metadata['abstract']}

Please help answer questions about this paper using the provided context."""
            
            st.session_state.messages.append({"role": "system", "content": system_msg})
            
            # Load existing chat history from Snowflake for this paper
            chat_history = load_chat_history(paper_id)
            st.session_state.messages.extend(chat_history)
        
        # Process next question if one was selected
        if "next_question" in st.session_state:
            question = st.session_state.next_question
            del st.session_state.next_question
            process_query(question, paper_id)
        
        # Display chat history
        for message in st.session_state.messages:
            if message["role"] != "system":  # Don't display system messages
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        
        # Chat input
        if prompt := st.chat_input("Ask a question about this paper"):
            process_query(prompt, paper_id)

def process_query(prompt: str, paper_id: str):
    """Process a query and generate response"""
    # Add user message to chat history and log to Snowflake
    st.session_state.messages.append({"role": "user", "content": prompt})
    log_chat_message(paper_id, "user", prompt)
    
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Get response using Snowflake Cortex
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            session = get_snowflake_session()
            root = Root(session)
            
            svc = root.databases[CORTEX_SEARCH_DATABASE].schemas[CORTEX_SEARCH_SCHEMA].cortex_search_services[CORTEX_SEARCH_SERVICE]
            
            # Get relevant chunks for the query
            filter_obj = {"@eq": {"PAPER_ID": paper_id}}
            response = svc.search(prompt, COLUMNS, filter=filter_obj, limit=NUM_CHUNKS)
            
            # Get recent conversation history (last 10 turns)
            recent_messages = [
                msg for msg in st.session_state.messages[-20:]
                if msg["role"] != "system"
            ]
            conversation_context = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in recent_messages
            ])
            
            # Generate response using Cortex Complete
            system_context = st.session_state.messages[0]["content"]
            prompt_text = f"""System Context: {system_context}

Recent Conversation:
{conversation_context}

Based on the following paper chunks: {response.json()}

User question: {prompt}

Please provide a clear and accurate answer based on the paper content and conversation history:"""
            
            response_text = Complete(
                model="mistral-large2",
                prompt=prompt_text,
                session=session
            )
            
            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            log_chat_message(paper_id, "assistant", response_text)

            # Generate suggested follow-up questions
            _generate_follow_up_questions(conversation_context, response_text, session)

def _generate_follow_up_questions(conversation_context: str, response_text: str, session):
    """Generate and display follow-up questions."""
    questions_prompt = f"""Based on this conversation history:
{conversation_context}

And the last response:
{response_text}

Generate 3 deep dive questions in JSON format like this:
{{
    "questions": {{
        "question1": '',
        "question2": '',
        "question3": ''
    }}
}}
DO NOT ADD COMMENTS OR ANYTHING ELSE TO THE JSON. ONLY THE JSON.
```json
"""
    
    questions_response = Complete(
        model="mistral-large2",
        prompt=questions_prompt,
        session=session
    )
    
    try:
        json_str = re.search(r'```json\s*(.*?)\s*```', questions_response, re.DOTALL)
        if json_str:
            questions_json = json.loads(json_str.group(1))
            
            # Simply display the suggested questions
            st.write("### Suggested follow-up questions:")
            for i, question in enumerate(questions_json['questions'].values(), 1):
                st.write(f"{i}. {question}")
    
    except (json.JSONDecodeError, AttributeError) as e:
        st.error(f"Failed to generate suggestions: {str(e)}")

def get_paper_metadata(paper_id: str) -> dict:
    """Fetch paper metadata from Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {CORTEX_SEARCH_DATABASE}").collect()
        session.sql(f"USE SCHEMA {CORTEX_SEARCH_SCHEMA}").collect()
        
        result = session.sql("""
            SELECT title, authors, published_date, abstract, categories, pdf_url
            FROM papers WHERE paper_id = ?
        """, params=(paper_id,)).collect()
        
        if result:
            row = result[0]
            return {
                'title': row[0],
                'authors': row[1],
                'published_date': row[2],
                'abstract': row[3],
                'categories': row[4],
                'pdf_url': row[5]
            }
        return None
    except Exception as e:
        st.error(f"Error fetching paper metadata: {e}")
        logger.error(f"Error fetching paper metadata: {e}")
        raise

def log_chat_message(paper_id: str, role: str, content: str):
    """Log a chat message to Snowflake."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {CORTEX_SEARCH_DATABASE}").collect()
        session.sql(f"USE SCHEMA {CORTEX_SEARCH_SCHEMA}").collect()
        
        # Insert chat message
        session.sql("""
            INSERT INTO chat_history (paper_id, role, content) 
            VALUES (?, ?, ?)
        """, params=(paper_id, role, content)).collect()
        
    except Exception as e:
        st.error(f"Error logging chat message: {e}")
        logger.error(f"Error logging chat message: {e}")

def load_chat_history(paper_id: str):
    """Load chat history for a specific paper."""
    session = get_snowflake_session()
    try:
        # Set context
        session.sql(f"USE DATABASE {CORTEX_SEARCH_DATABASE}").collect()
        session.sql(f"USE SCHEMA {CORTEX_SEARCH_SCHEMA}").collect()
        
        # Get chat history
        result = session.sql("""
            SELECT role, content 
            FROM chat_history 
            WHERE paper_id = ? 
            ORDER BY timestamp ASC
        """, params=(paper_id,)).collect()
        
        return [{"role": row[0], "content": row[1]} for row in result]
        
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        logger.error(f"Error loading chat history: {e}")
        return []

def generate_paper_summary(paper_id: str, metadata: dict) -> str:
    """Generate a detailed summary of the paper using deep-dive questions."""
    session = get_snowflake_session()
    root = Root(session)
    chunk_svc = root.databases[CORTEX_SEARCH_DATABASE].schemas[CORTEX_SEARCH_SCHEMA].cortex_search_services[CORTEX_SEARCH_SERVICE]
    
    # Generate deep dive questions
    questions_prompt = f"""Given this research paper abstract: {metadata['abstract']}
    Generate 3 deep dive questions about the paper's content in JSON format like this:
    {{
        "questions": {{
            "question1": "First question here",
            "question2": "Second question here",
            "question3": "Third question here"
        }}
    }}
    DO NOT ADD COMMENTS OR ANYTHING ELSE TO THE JSON. ONLY THE JSON.
    ```json
    """
    
    questions_response = Complete(
        model="mistral-large2",
        prompt=questions_prompt,
        session=session
    )
    
    qa_pairs = []
    try:
        json_str = re.search(r'```json\s*(.*?)\s*```', questions_response, re.DOTALL)
        if json_str:
            questions_json = json.loads(json_str.group(1))
            for question in questions_json['questions'].values():
                filter_obj = {"@eq": {"PAPER_ID": paper_id}}
                chunk_response = chunk_svc.search(
                    question, 
                    ["CHUNK_TEXT", "PAPER_ID"], 
                    filter=filter_obj, 
                    limit=3
                )
                
                chunks = chunk_response.results
                chunk_texts = [chunk['CHUNK_TEXT'] for chunk in chunks]
                
                answer_prompt = f"""Based on these relevant sections from the paper:
                {chunk_texts}
                
                Please answer this question: {question}
                Provide a detailed answer in 2-3 sentences."""
                
                answer = Complete(
                    model="mistral-large2",
                    prompt=answer_prompt,
                    session=session
                )
                
                qa_pairs.append({
                    "question": question,
                    "answer": answer,
                    "relevant_chunks": chunk_texts
                })
        
        # Generate final summary
        if qa_pairs:
            deep_analysis = "\n".join(
                [f"Question: {qa['question']}\nAnswer: {qa['answer']}\nRelevant Text: {qa['relevant_chunks']}" 
                 for qa in qa_pairs]
            )
            summary_prompt = f"""Based on the following information about a research paper:

            Abstract:
            {metadata['abstract']}

            Deep Analysis:
            {deep_analysis}

            Please provide a comprehensive analysis of the paper in a structured bullet-point format

            

            Format each bullet point as a complete, informative statement. Incorporate specific details from both the abstract and the deep-dive Q&A analysis.
            Focus on technical details and insights that weren't immediately apparent from the abstract alone.
            """

            return Complete(
                model="mistral-large2",
                prompt=summary_prompt,
                session=session
            )
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
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