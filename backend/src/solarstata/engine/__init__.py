"""Statistical engine — pure computation, no AI.

Module layering matches Stata's C-core / Mata / ado-file split,
adapted for Python:

  - results.py     :: e()/r() namespaces (parallel to Stata's stored results)
  - formatters.py  :: Stata-style ASCII output renderers
  - descriptive.py :: summarize, summarize, detail
  - tabulate.py    :: one-way and two-way tabulate

Everything in here takes a pandas DataFrame in and returns a Result
(structured payload + Stata-style text + r()/e() update).
"""

from .descriptive import summarize
from .results import Result, ResultsStore
from .tabulate import tabulate

__all__ = ["Result", "ResultsStore", "summarize", "tabulate"]
