import argparse
import csv
import sys
from sqlalchemy import select
from tabulate import tabulate
from app.db import SessionLocal, Course

def add_cmd(args):
    code = args.code.upper().strip()
    with SessionLocal() as session:
        existing = session.get(Course, code)
        if existing:
            print(f"Course {code} already exists.")
            sys.exit(1)
            
        course = Course(
            code=code,
            title=args.title,
            level=args.level,
            department=args.department,
            is_active=True
        )
        session.add(course)
        session.commit()
        print(f"Added course {code}")

def list_cmd(args):
    with SessionLocal() as session:
        query = select(Course)
        if not args.include_inactive:
            query = query.where(Course.is_active == True)
            
        courses = session.execute(query).scalars().all()
        
        headers = ["code", "title", "level", "department", "is_active"]
        rows = [[c.code, c.title, c.level, c.department, c.is_active] for c in courses]
        
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        else:
            print(tabulate(rows, headers=headers))

def deactivate_cmd(args):
    code = args.code.upper().strip()
    with SessionLocal() as session:
        course = session.get(Course, code)
        if not course:
            print(f"Course {code} not found.")
            sys.exit(1)
            
        if not course.is_active:
            print(f"Course {code} is already inactive.")
            sys.exit(0)
            
        if not args.yes:
            confirm = input(f"Deactivate {code}? Type 'yes' to confirm: ")
            if confirm != "yes":
                print("Aborted.")
                sys.exit(2)
                
        course.is_active = False
        session.commit()
        print(f"Deactivated {code}")

def main():
    parser = argparse.ArgumentParser(description="Manage course catalog.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    p_add = subparsers.add_parser("add")
    p_add.add_argument("code")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--level", type=int, choices=[100, 200, 300, 400], required=True)
    p_add.add_argument("--department", required=True)
    
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--include-inactive", action="store_true")
    p_list.add_argument("--csv", metavar="PATH")
    
    p_deact = subparsers.add_parser("deactivate")
    p_deact.add_argument("code")
    p_deact.add_argument("--yes", action="store_true")
    
    args = parser.parse_args()
    
    if args.subcommand == "add":
        add_cmd(args)
    elif args.subcommand == "list":
        list_cmd(args)
    elif args.subcommand == "deactivate":
        deactivate_cmd(args)

if __name__ == "__main__":
    main()