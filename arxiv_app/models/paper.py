from dataclasses import dataclass
from typing import List
import pandas as pd

@dataclass
class CachedSearch:
    query: str
    max_results: int
    papers: List[dict]
    papers_df: pd.DataFrame 