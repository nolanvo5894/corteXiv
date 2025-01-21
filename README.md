# corteXiv 🧊

A modern interface for exploring and interacting with arXiv papers, powered by Snowflake Cortex and LLMs.

## 🌟 Features

### 📚 Paper Search & Management
- Search arXiv papers with relevance and recency ranking
- Save papers to your personal library
- Organize and search for papers by metadata
- Semantic search through your saved papers using Snowflake Cortex
- Smart paper recommendations based on your library content

### 💬 Interactive Paper Chat
- Chat with any paper in your library
- Get instant answers about paper content
- AI-generated deep dive questions
- Conversation memory.
- AI-generated paper summaries and key insights. Key insights comes from the LLM 

## 🛠 Technology Stack

- **Frontend**: Streamlit
- **Backend**: 
  - Snowflake for data storage
  - Snowflake Cortex for smart hybrid search and LLM access
  - Mistral LLM for chat interactions
  - Trulens for experimenting with RAG strategies
- **Document Processing**:
  - Docling for document conversion
  - LangChain for text chunking
- **APIs**: arXiv API for paper retrieval

## 🧠 Technical Details

### Snowflake Cortex Integration

#### Vector Search
- Papers are automatically parsed and chunked upon addition to library
- Cortex Search service indexes both full abstracts and paper chunks
- Hybrid search combines:
  - Vector similarity for semantic understanding
  - Keyword matching for precision
  - Relevance scoring for result ranking

#### LLM Integration
- Uses Mistral Large v2 model through Snowflake Cortex
- Used for:
  - simple RAG for Paper Chat and Cortex Search Summary
  - structured output for suggesting deep dive questions
  - multi-step agentic RAG for Paper Key Insights
  - intelligent paper recommendations based on library analysis

### Chat System Architecture

#### Context Retrieval
- Dynamic chunk selection based on query relevance
- Maintains conversation history for context
- Uses sliding window for recent chat memory
- Balances context length with response quality

#### Paper Insights Generation
- Multi-step analysis process:
  1. Generate targeted deep-dive questions
  2. Search for relevant chunks per question
  3. Synthesize answers with source context
  4. Compile comprehensive insights summary

### RAG Optimization
- Uses Trulens for:
  - Evaluating retrieval quality
  - Testing different chunking strategies
  - Measuring answer relevance
  - Monitoring hallucination rates

## 📁 Project Structure

```
corteXiv/
├── arxiv_app/                  # Main application directory
│   ├── main.py                # Application entry point and UI
│   ├── config.py              # Configuration settings
│   ├── services/             # Core services
│   │   ├── arxiv_service.py  # arXiv API interaction
│   │   ├── chat_service.py   # LLM chat functionality
│   │   └── pdf_service.py    # PDF processing and storage
│   ├── database/             # Database operations
│   │   └── snowflake_manager.py  # Snowflake interactions
│   ├── models/               # Data models
│   │   └── paper.py         # Paper data structures
│   └── utils/               # Utility functions
│       ├── html_to_md.py    # HTML to Markdown conversion
│       └── logging_config.py # Logging setup
├── requirements.txt          # Project dependencies
└── .gitignore               # Git ignore rules
```

### Key Components

#### Core Files
- `main.py`: Main Streamlit application with UI components and page routing
- `config.py`: Configuration settings for Snowflake, Cortex, and chunking parameters

#### Services
- `arxiv_service.py`: 
  - Handles arXiv API queries
  - Paper metadata retrieval
  - Search result processing

- `chat_service.py`:
  - Manages chat interactions with papers
  - Integrates with Snowflake Cortex
  - Handles context retrieval and LLM responses
  - Generates paper summaries and insights

- `pdf_service.py`:
  - Processes PDF documents
  - Extracts and chunks text
  - Manages document storage

#### Database
- `snowflake_manager.py`:
  - Manages Snowflake connections
  - Handles database operations
  - Implements data models and tables
  - Manages chat history and paper storage

#### Utilities
- `html_to_md.py`: Converts arXiv HTML to markdown format
- `logging_config.py`: Configures application logging

#### Experimental
- `trulens_*.py`: Scripts for RAG experimentation and evaluation using Trulens

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Snowflake account with Cortex enabled
- Streamlit account (for secrets management)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/corteXiv.git
cd corteXiv
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure Snowflake credentials:
Create `.streamlit/secrets.toml` with:
```toml
[snowflake]
user = "your_username"
password = "your_password"
account = "your_account"
```

4. Run the application:
```bash
streamlit run arxiv_app/main.py
```

## 🎯 Usage

1. **Search Papers**: 
   - Use the search page to find papers on arXiv
   - Results are sorted by relevance and date
   - Add interesting papers to your library

2. **Personal Library**:
   - Access your saved papers
   - Use metadata search for basic filtering
   - Use Cortex search for semantic similarity
   - Chat with any saved paper

3. **Paper Chat**:
   - Ask questions about the paper
   - Get contextual answers
   - Follow suggested questions
   - View paper summaries and insights

## 📝 License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Snowflake](https://www.snowflake.com/) and [Streamlit](https://streamlit.io/)
- Paper metadata from [arXiv](https://arxiv.org/)
- LLM capabilities powered by Mistral