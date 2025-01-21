from trulens.core import TruSession
from trulens.dashboard import run_dashboard
import pandas as pd

session = TruSession() # or default.sqlite by default
pd.DataFrame(session.get_records_and_feedback()[0]).to_csv('trulens_records.csv', index=False)
run_dashboard(session)
