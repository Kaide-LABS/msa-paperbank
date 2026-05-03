import argparse
import csv
import sys
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, Paper

def main():
    parser = argparse.ArgumentParser(description="List papers.")
    parser.add_argument("--year", type=int)
    parser.add_argument("--semester", choices=["harmattan", "rain"])
    parser.add_argument("--session", choices=["CA1", "CA2", "exam"])
    parser.add_argument("--include-retired", action="store_true")
    parser.add_argument("--csv", type=str, metavar="PATH")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    with SessionLocal() as session:
        query = select(Paper)
        
        if not args.include_retired:
            query = query.where(Paper.is_retired == False)
            
        if args.year:
            query = query.where(Paper.year == args.year)
        if args.semester:
            query = query.where(Paper.semester.ilike(args.semester))
        if args.session:
            query = query.where(Paper.exam_session.ilike(args.session))
            
        query = query.order_by(Paper.id.desc()).limit(args.limit)
        papers = session.execute(query).scalars().all()
        
        headers = ["id", "course", "year", "semester", "session", "gcs_object", "is_active_risk", "held_until", "is_retired", "uploaded_at"]
        rows = []
        for p in papers:
            rows.append([
                p.id, p.course_code, p.year, p.semester, p.exam_session, p.gcs_object,
                p.is_active_risk, p.held_until, p.is_retired, p.uploaded_at
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