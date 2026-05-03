import argparse
import sys
import json
import csv
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, User, UserTombstone, RequestLog

def get_cmd(args):
    phone = args.phone.strip().replace("+", "")
    with SessionLocal() as session:
        user = session.get(User, phone)
        tombstone = session.get(UserTombstone, phone)
        
        print(f"--- Profile for {phone} ---")
        if user:
            print(f"interaction_count: {user.interaction_count}")
            print(f"last_seen_at: {user.last_seen_at}")
            print(f"privacy_notice_sent_at: {user.privacy_notice_sent_at}")
            print(f"inferred_courses: {json.dumps(user.inferred_courses)}")
        else:
            print("No active user row found.")
            
        print(f"opted_out_at: {user.opted_out_at if user else (tombstone.opted_out_at if tombstone else 'None')}")
        print(f"tombstoned: {'Y' if tombstone else 'N'}")

def list_cmd(args):
    with SessionLocal() as session:
        query = select(User).order_by(User.last_seen_at.desc())
        users = session.execute(query.limit(args.limit)).scalars().all()
        
        headers = ["phone_number", "interaction_count", "last_seen_at", "inferred_courses"]
        rows = [[u.phone_number, u.interaction_count, u.last_seen_at, json.dumps(u.inferred_courses)] for u in users]
        
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        else:
            print(tabulate(rows, headers=headers))
            
        if args.include_tombstoned:
            tombstones = session.execute(select(UserTombstone).limit(args.limit)).scalars().all()
            print("\n--- Tombstones ---")
            t_headers = ["phone_number", "opted_out_at", "last_keyword"]
            t_rows = [[t.phone_number, t.opted_out_at, t.last_keyword] for t in tombstones]
            print(tabulate(t_rows, headers=t_headers))

def reset_cmd(args):
    phone = args.phone.strip().replace("+", "")
    with SessionLocal() as session:
        user = session.get(User, phone)
        if not user:
            print("User not found.")
            sys.exit(1)
            
        if not args.yes:
            confirm = input(f"Reset interaction_count and inferred_courses for {phone}? Type 'yes': ")
            if confirm != "yes":
                print("Aborted.")
                sys.exit(2)
                
        user.interaction_count = 0
        user.inferred_courses = {}
        session.commit()
        print("Profile reset.")

def export_cmd(args):
    phone = args.phone.strip().replace("+", "")
    with SessionLocal() as session:
        user = session.get(User, phone)
        tombstone = session.get(UserTombstone, phone)
        logs = session.execute(
            select(RequestLog)
            .where(RequestLog.wa_from == phone)
            .order_by(RequestLog.received_at.desc())
            .limit(50)
        ).scalars().all()
        
        out = {
            "phone_number": phone,
            "user": None,
            "tombstone": None,
            "logs": []
        }
        
        if user:
            out["user"] = {
                "inferred_courses": user.inferred_courses,
                "interaction_count": user.interaction_count,
                "created_at": user.created_at.isoformat(),
                "last_seen_at": user.last_seen_at.isoformat(),
                "privacy_notice_sent_at": user.privacy_notice_sent_at.isoformat() if user.privacy_notice_sent_at else None,
                "opted_out_at": user.opted_out_at.isoformat() if user.opted_out_at else None
            }
            
        if tombstone:
            out["tombstone"] = {
                "opted_out_at": tombstone.opted_out_at.isoformat(),
                "last_keyword": tombstone.last_keyword
            }
            
        for l in logs:
            out["logs"].append({
                "received_at": l.received_at.isoformat(),
                "user_text": l.user_text,
                "routed_course": l.routed_course,
                "outcome": l.outcome,
                "error": l.error
            })
            
        j = json.dumps(out, indent=2)
        if args.out:
            with open(args.out, "w") as f:
                f.write(j)
            print(f"Exported to {args.out}")
        else:
            print(j)

def main():
    parser = argparse.ArgumentParser(description="Manage users and privacy.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    p_get = subparsers.add_parser("get")
    p_get.add_argument("phone")
    
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--csv", metavar="PATH")
    p_list.add_argument("--include-tombstoned", action="store_true")
    
    p_reset = subparsers.add_parser("reset")
    p_reset.add_argument("phone")
    p_reset.add_argument("--yes", action="store_true")
    
    p_export = subparsers.add_parser("export")
    p_export.add_argument("phone")
    p_export.add_argument("--out", metavar="PATH")
    
    args = parser.parse_args()
    
    if args.subcommand == "get":
        get_cmd(args)
    elif args.subcommand == "list":
        list_cmd(args)
    elif args.subcommand == "reset":
        reset_cmd(args)
    elif args.subcommand == "export":
        export_cmd(args)

if __name__ == "__main__":
    main()