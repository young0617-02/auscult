"""一次性数据清洗：alerts 表 severity 口径对齐前端契约（high/medium/low → critical/warning/info）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.db import get_conn

with get_conn() as conn:
    n1 = conn.execute("UPDATE alerts SET severity='critical' WHERE severity='high'").rowcount
    n2 = conn.execute("UPDATE alerts SET severity='warning' WHERE severity='medium'").rowcount
    n3 = conn.execute("UPDATE alerts SET severity='info' WHERE severity='low'").rowcount
    conn.commit()
    rows = conn.execute("SELECT severity, count(*) FROM alerts GROUP BY severity ORDER BY 1").fetchall()

print(f"high->critical: {n1}, medium->warning: {n2}, low->info: {n3}")
for r in rows:
    print(dict(r))
