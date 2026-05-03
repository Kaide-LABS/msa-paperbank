import argparse
import csv
import sys
import os
from datetime import datetime, timezone
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, Uploader

def allow_cmd(args):
    phone = args.phone.strip().replace("+", "")
    with SessionLocal() as session:
        existing = session.get(Uploader, phone)
        if existing:
            if existing.revoked_at is not None:
                existing.revoked_at = None
                existing.revoke_reason = None
                session.commit()
                print(f"Un-revoked {phone}")
            else:
                print(f"Uploader {phone} already allowed.")
        else:
            uploader = Uploader(
                phone_number=phone,
                display_name=args.name,
                added_by=os.environ.get("USER", "ibrahim")
            )
            session.add(uploader)
            session.commit()
            print(f"Allowed {phone}")

def revoke_cmd(args):
    phone = args.phone.strip().replace("+", "")
    with SessionLocal() as session:
        existing = session.get(Uploader, phone)
        if not existing:
            print(f"Uploader {phone} not found.")
            sys.exit(1)
            
        if existing.revoked_at is not None:
            print(f"Uploader {phone} is already revoked.")
            sys.exit(0)
            
        if not args.yes:
            confirm = input(f"Revoke {phone}? Type 'yes' to confirm: ")
            if confirm != "yes":
                print("Aborted.")
                sys.exit(2)
                
        existing.revoked_at = datetime.now(timezone.utc)
        existing.revoke_reason = args.reason
        session.commit()
        print(f"Revoked {phone}")

def list_cmd(args):
    with SessionLocal() as session:
        query = select(Uploader)
        if not args.include_revoked:
            query = query.where(Uploader.revoked_at == None)
            
        uploaders = session.execute(query).scalars().all()
        
        headers = ["phone_number", "display_name", "added_by", "added_at", "revoked_at", "revoke_reason"]
        rows = [[u.phone_number, u.display_name, u.added_by, u.added_at, u.revoked_at, u.revoke_reason] for u in uploaders]
        
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        else:
            print(tabulate(rows, headers=headers))

def main():
    parser = argparse.ArgumentParser(description="Manage uploaders whitelist.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    p_allow = subparsers.add_parser("allow")
    p_allow.add_argument("phone")
    p_allow.add_argument("--name", type=str)
    
    p_revoke = subparsers.add_parser("revoke")
    p_revoke.add_argument("phone")
    p_revoke.add_argument("--reason", required=True)
    p_revoke.add_argument("--yes", action="store_true")
    
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--include-revoked", action="store_true")
    p_list.add_argument("--csv", metavar="PATH")
    
    args = parser.parse_args()
    
    if args.subcommand == "allow":
        allow_cmd(args)
    elif args.subcommand == "revoke":
        revoke_cmd(args)
    elif args.subcommand == "list":
        list_cmd(args)

if __name__ == "__main__":
    main()