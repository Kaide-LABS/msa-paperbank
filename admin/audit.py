import argparse
import csv
import sys
from datetime import datetime
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, RequestLog

def main():
    parser = argparse.ArgumentParser(description="Audit request log.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--since", type=str, help="YYYY-MM-DD")
    group.add_argument("--phone", type=str, help="E164 phone number")
    
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--csv", type=str, metavar="PATH")
    args = parser.parse_args()

    with SessionLocal() as session:
        query = select(RequestLog).order_by(RequestLog.received_at.desc())
        
        if args.since:
            try:
                dt = datetime.strptime(args.since, "%Y-%m-%d")
                query = query.where(RequestLog.received_at >= dt)
            except ValueError:
                print("Invalid date format, use YYYY-MM-DD")
                sys.exit(1)
        elif args.phone:
            query = query.where(RequestLog.wa_from == args.phone)
            
        query = query.limit(args.limit)
        logs = session.execute(query).scalars().all()
        
        headers = ["received_at", "wa_from", "user_text", "routed_course", "routed_year", "routed_semester", "outcome", "matched_paper_id", "flash_input_tokens", "flash_output_tokens", "error"]
        rows = []
        for r in logs:
            rows.append([
                r.received_at, r.wa_from, r.user_text, r.routed_course, r.routed_year, r.routed_semester,
                r.outcome, r.matched_paper_id, r.flash_input_tokens, r.flash_output_tokens, r.error
            ])
            
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        else:
            print(tabulate(rows, headers=headers))
            
if __name__ == "__main__":
    main()