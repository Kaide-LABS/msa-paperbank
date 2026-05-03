import argparse
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import select
from app.db import SessionLocal, Paper

def main():
    parser = argparse.ArgumentParser(description="Retire a past paper or all papers for a course.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("paper_id", type=int, nargs="?", help="ID of the paper to retire")
    group.add_argument("--course", type=str, help="Course code to mass-retire")
    
    parser.add_argument("--reason", type=str, required=True, help="Reason for retirement")
    parser.add_argument("--yes", action="store_true", help="Confirm without prompting")
    args = parser.parse_args()

    user = os.environ.get("USER", "ibrahim")
    now_dt = datetime.now(timezone.utc)

    with SessionLocal() as session:
        if args.course:
            code = args.course.upper().strip()
            papers = session.execute(
                select(Paper).where(Paper.course_code == code, Paper.is_retired == False)
            ).scalars().all()
            
            if not papers:
                print(f"No active papers found for course {code}")
                sys.exit(0)
                
            print(f"Found {len(papers)} active papers for {code}:")
            for p in papers:
                print(f"  - id={p.id} ({p.year} {p.semester})")
                
            if not args.yes:
                confirm = input("Type 'yes' to confirm mass retirement: ")
                if confirm != "yes":
                    print("Aborted.")
                    sys.exit(2)
                    
            for p in papers:
                p.is_retired = True
                p.retired_by = user
                p.retired_at = now_dt
                p.retired_reason = args.reason
            session.commit()
            print(f"✓ Mass retired {len(papers)} papers for {code} by {user}")
            
        else:
            paper = session.get(Paper, args.paper_id)
            if not paper:
                print("paper not found")
                sys.exit(1)
                
            print(f"Paper: id={paper.id}, course={paper.course_code}, year={paper.year}, semester={paper.semester}, gcs_object={paper.gcs_object}, is_retired={paper.is_retired}")
            
            if paper.is_retired:
                print("already retired")
                sys.exit(0)
                
            if not args.yes:
                confirm = input("Type 'yes' to confirm: ")
                if confirm != "yes":
                    print("Aborted.")
                    sys.exit(2)
                    
            paper.is_retired = True
            paper.retired_by = user
            paper.retired_at = now_dt
            paper.retired_reason = args.reason
            session.commit()
            
            print(f"✓ Retired paper_id={paper.id} by {user} at {now_dt.isoformat()}")

if __name__ == "__main__":
    main()