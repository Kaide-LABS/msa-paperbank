import argparse
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, RequestLog

def run_tail(minutes: int, errors_only: bool, limit: int):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    
    stmt = select(RequestLog).where(RequestLog.received_at >= cutoff)
    if errors_only:
        stmt = stmt.where(RequestLog.outcome.in_(['error', 'rate_limited']))
        
    stmt = stmt.order_by(RequestLog.received_at.desc()).limit(limit)
    
    with SessionLocal() as session:
        rows = session.execute(stmt).scalars().all()
        
    table = []
    for r in rows:
        phone_masked = r.wa_from[:-4] + "XXXX" if len(r.wa_from) > 4 else r.wa_from
        table.append([
            r.received_at.strftime("%Y-%m-%d %H:%M:%S"),
            phone_masked,
            r.outcome,
            r.routed_course or "-",
            r.error or "-"
        ])
        
    headers = ["Received At", "From", "Outcome", "Course", "Error"]
    print(tabulate(table, headers=headers, tablefmt="github"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tail recent request logs")
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--errors-only", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    
    run_tail(args.minutes, args.errors_only, args.limit)
