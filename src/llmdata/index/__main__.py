"""python -m llmdata.index hash"""

from __future__ import annotations

import argparse

from llmdata.config import settings
from llmdata.db import connect
from llmdata.index import index_hash

parser = argparse.ArgumentParser(prog="llmdata.index")
parser.add_argument("command", choices=["hash"])
parser.parse_args()
with connect(settings().dsn) as conn:
    value, count = index_hash(conn)
print(f"{value} {count}")
