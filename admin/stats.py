import argparse
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text
from tabulate import tabulate
from app.db import SessionLocal, RequestLog, Paper

def main():
    parser = argparse.ArgumentParser(description="Show stats.")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    
    with SessionLocal() as session:
        # Total requests
        total_reqs = session.execute(select(func.count(RequestLog.id)).where(RequestLog.received_at >= since)).scalar()
        
        # Outcomes
        outcomes = session.execute(
            select(RequestLog.outcome, func.count(RequestLog.id))
            .where(RequestLog.received_at >= since)
            .group_by(RequestLog.outcome)
        ).all()
        
        # Tokens
        tokens = session.execute(
            select(
                func.coalesce(func.sum(RequestLog.flash_input_tokens), 0),
                func.coalesce(func.sum(RequestLog.flash_output_tokens), 0)
            ).where(RequestLog.received_at >= since)
        ).first()
        in_tok, out_tok = tokens if tokens else (0, 0)
        
        # Top 10 requested
        top_10 = session.execute(
            select(
                RequestLog.routed_course, RequestLog.routed_year, RequestLog.routed_semester, func.count(RequestLog.id).label('hits')
            )
            .where(RequestLog.received_at >= since, RequestLog.outcome == 'sent')
            .group_by(RequestLog.routed_course, RequestLog.routed_year, RequestLog.routed_semester)
            .order_by(text('hits DESC'))
            .limit(10)
        ).all()
        
        # Total papers
        live_papers = session.execute(select(func.count(Paper.id)).where(Paper.is_retired == False)).scalar()
        
        print("=== Overview ===")
        print(tabulate([
            ["Days window", args.days],
            ["Total Requests", total_reqs],
            ["Total Flash Tokens", in_tok + out_tok],
            ["Live Papers in DB", live_papers]
        ]))
        print("\n=== Outcomes ===")
        print(tabulate(outcomes, headers=["Outcome", "Count"]))
        print("\n=== Top 10 Requests (Sent) ===")
        print(tabulate(top_10, headers=["Course", "Year", "Semester", "Hits"]))

if __name__ == "__main__":
    main()