import argparse
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import select
from app.db import SessionLocal, Paper

def main():
    parser = argparse.ArgumentParser(description="Retire a past paper.")
    parser.add_argument("paper_id", type=int, help="ID of the paper to retire")
    parser.add_argument("--reason", type=str, required=True, help="Reason for retirement")
    parser.add_argument("--yes", action="store_true", help="Confirm without prompting")
    args = parser.parse_args()

    with SessionLocal() as session:
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
                
        user = os.environ.get("USER", "ibrahim")
        now_dt = datetime.now(timezone.utc)
        
        paper.is_retired = True
        paper.retired_by = user
        paper.retired_at = now_dt
        paper.retired_reason = args.reason
        session.commit()
        
        print(f"✓ Retired paper_id={paper.id} by {user} at {now_dt.isoformat()}")

if __name__ == "__main__":
    main()