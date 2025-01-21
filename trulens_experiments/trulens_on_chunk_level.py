import os
import numpy as np
import streamlit as st
from snowflake.snowpark.session import Session
from snowflake.core import Root
from snowflake.cortex import Summarize, Complete
from typing import List
from trulens.core import TruSession
from trulens.apps.custom import instrument
from trulens.providers.cortex.provider import Cortex
from trulens.core import Feedback
from trulens.core import Select
from trulens.apps.custom import TruCustomApp
from trulens.connectors.snowflake import SnowflakeConnector

from trulens.core.guardrails.base import context_filter
from trulens.dashboard import run_dashboard
import trulens.dashboard.streamlit as trulens_st


# Snowflake configuration
CONNECTION_PARAMETERS = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"],
    "role": "ACCOUNTADMIN",
    "database": "ARXIV_PAPERS_DB",
    "schema": "ARXIV_PAPERS_SCHEMA"
}


# service parameters
CORTEX_SEARCH_DATABASE = "TEST_PAPERS_DB"
CORTEX_SEARCH_SCHEMA = "TEST_PAPERS_SCHEMA"
CORTEX_SEARCH_SERVICES = {
    256: "TEST_ARXIV_SEARCH_SERVICE_CHUNKS_256_CS",
    512: "TEST_ARXIV_SEARCH_SERVICE_CHUNKS_512_CS",
    1024: "TEST_ARXIV_SEARCH_SERVICE_CHUNKS_1024_CS"
}

class CortexSearchRetriever:

    def __init__(self, snowpark_session: Session, limit_to_retrieve: int, chunk_size: int):
        self._snowpark_session = snowpark_session
        self._limit_to_retrieve = limit_to_retrieve
        self._chunk_size = chunk_size

    def retrieve(self, query: str) -> List[str]:
        root = Root(self._snowpark_session)
        cortex_search_service = (
            root.databases[CORTEX_SEARCH_DATABASE]
            .schemas[CORTEX_SEARCH_SCHEMA]
            .cortex_search_services[CORTEX_SEARCH_SERVICES[self._chunk_size]]
        )
        resp = cortex_search_service.search(
            query=query,
            columns=["CHUNK_TEXT"],
            limit=self._limit_to_retrieve,
        )

        if resp.results:
            return [curr["CHUNK_TEXT"] for curr in resp.results]
        else:
            return []



snowpark_session = Session.builder.configs(CONNECTION_PARAMETERS).create()

# tru_snowflake_connector = SnowflakeConnector(snowpark_session=snowpark_session)

# tru_session = TruSession(connector=tru_snowflake_connector)
tru_session = TruSession()
tru_session.reset_database()

class RAG_from_scratch:

    def __init__(self, limit_to_retrieve: int, chunk_size: int):
        self.retriever = CortexSearchRetriever(
            snowpark_session=snowpark_session, 
            limit_to_retrieve=limit_to_retrieve,
            chunk_size=chunk_size
        )

    @instrument
    def retrieve_context(self, query: str) -> list:
        """
        Retrieve relevant text from vector store.
        """
        return self.retriever.retrieve(query)

   

    @instrument
    def generate_completion(self, query: str, context_documents: list) -> str:
        """
        Generate answer from context.
        """
        prompt = f"""
        You are an expert assistant extracting information from context
    provided.
        Answer the question based on the context. Be concise and do not
    hallucinate.
        If you don ́t have the information just say so.
        Context: {context_documents}
        Question:
        {query}
    Answer: """
        return Complete("mistral-large2", prompt)

    @instrument
    def query(self, query: str) -> str:
        context_str = self.retrieve_context(query)
        return self.generate_completion(query, context_str)
    
provider = Cortex(snowpark_session, "mistral-large2")

f_groundedness = (
    Feedback(provider.groundedness_measure_with_cot_reasons, name="Groundedness")
    .on(Select.RecordCalls.retrieve_context.rets[:].collect())
    .on_output()
)

f_context_relevance = (
    Feedback(provider.context_relevance, name="Context Relevance")
    .on_input()
    .on(Select.RecordCalls.retrieve_context.rets[:])
    .aggregate(np.mean)
)

f_answer_relevance = (
    Feedback(provider.relevance, name="Answer Relevance")
    .on_input()
    .on_output()
    .aggregate(np.mean)
)

questions = [
    
    "What is the main goal of the DiMA framework proposed in the paper?",
    "How does DiMA address the challenges of computational overhead associated with LLM-based planners?",
    "What are the two main components of the DiMA framework?",
    "What role does the vision-based planner play in the DiMA system?",
    "What are BEAM token embeddings, and how are they used in the framework?",
    "What is the purpose of the surrogate tasks introduced in DiMA, such as masked token reconstruction and future BEV prediction?",
    "How does DiMA achieve state-of-the-art performance on the nuScenes planning benchmark?",
    "What datasets are used to train and evaluate the DiMA framework, and how are they utilized?",
    "What is the significance of the joint-training approach used in DiMA, and what does it involve?",
    "How does DiMA enable efficient planning inference while leveraging the knowledge of a multi-modal LLM?"
]



# Run experiments for each chunk size and number of chunks to retrieve
chunk_sizes = [256, 512, 1024]
for chunk_size in chunk_sizes:
    for i in range(3, 10):
        rag = RAG_from_scratch(limit_to_retrieve=i, chunk_size=chunk_size)
        tru_rag = TruCustomApp(
            rag,
            app_name=f"simple_RAG",
            app_version=f"chunk_size_{chunk_size}_n_chunks_{i}",
            feedbacks=[f_groundedness, f_answer_relevance, f_context_relevance],
        )
        with tru_rag as recording:
            for prompt in questions:
                rag.query(prompt)  





f_context_relevance_score = Feedback(
    provider.context_relevance, name="Context Relevance"
)


class filtered_RAG_from_scratch(RAG_from_scratch):

    @instrument
    @context_filter(f_context_relevance_score, 0.75, keyword_for_prompt="query")
    def retrieve_context(self, query: str) -> list:
        """
        Retrieve relevant text from vector store.
        """
        return self.retriever.retrieve(query)

















# Run experiments with filtered RAG for each chunk size and number of chunks to retrieve
for chunk_size in chunk_sizes:
    for i in range(3, 10):
        filtered_rag = filtered_RAG_from_scratch(limit_to_retrieve=i, chunk_size=chunk_size)
        tru_filtered_rag = TruCustomApp(
            filtered_rag,
            app_name=f"filtered_RAG",
            app_version=f"chunk_size_{chunk_size}_n_chunks_{i}",
            feedbacks=[f_groundedness, f_answer_relevance, f_context_relevance],
        )
        with tru_filtered_rag as recording:
            for prompt in questions:
                filtered_rag.query(prompt)

run_dashboard(tru_session)













