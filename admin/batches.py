import argparse
import sys
from sqlalchemy import select, func
from tabulate import tabulate
from app.db import SessionLocal, ImageBatch, ImageBatchItem
from app.config import settings
from app.providers import get_object_store
from app.intake import sweep_and_seal_single

def list_cmd(args):
    with SessionLocal() as session:
        query = select(ImageBatch).order_by(ImageBatch.id.desc())
        if args.phone:
            query = query.where(ImageBatch.phone_number == args.phone)
        if args.status:
            query = query.where(ImageBatch.status == args.status)
            
        query = query.limit(args.limit)
        batches = session.execute(query).scalars().all()
        
        headers = ["id", "phone_number", "status", "opened_at", "last_item_at", "sealed_at", "items_count"]
        rows = []
        for b in batches:
            items_count = session.execute(select(func.count(ImageBatchItem.id)).where(ImageBatchItem.batch_id == b.id)).scalar()
            rows.append([b.id, b.phone_number, b.status, b.opened_at, b.last_item_at, b.sealed_at, items_count])
            
        print(tabulate(rows, headers=headers))

def seal_cmd(args):
    with SessionLocal() as session:
        batch = session.get(ImageBatch, args.batch_id)
        if not batch:
            print(f"Batch {args.batch_id} not found.")
            sys.exit(1)
            
        if batch.status not in ('open', 'deferred_ocr'):
            print(f"Batch {args.batch_id} is in status '{batch.status}', not 'open' or 'deferred_ocr'.")
            sys.exit(1)
            
        if not args.yes:
            confirm = input(f"Seal batch {args.batch_id}? Type 'yes' to confirm: ")
            if confirm != "yes":
                print("Aborted.")
                sys.exit(2)
                
        # Force open status for the sealer if deferred
        batch.status = 'open'
        session.commit()
        
    store = get_object_store(settings)
    with SessionLocal() as session:
        sweep_and_seal_single(session, store, args.batch_id)
        print(f"Sealed batch {args.batch_id}")

def clear_cmd(args):
    with SessionLocal() as session:
        batch = session.get(ImageBatch, args.batch_id)
        if not batch:
            print(f"Batch {args.batch_id} not found.")
            sys.exit(1)
            
        if not args.yes:
            confirm = input(f"Clear batch {args.batch_id}? Type 'yes' to confirm: ")
            if confirm != "yes":
                print("Aborted.")
                sys.exit(2)
                
        batch.status = 'failed'
        batch.failure_reason = args.reason
        session.commit()
        print(f"Cleared batch {args.batch_id} (marked as failed)")

def main():
    parser = argparse.ArgumentParser(description="Manage image batches.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--phone", type=str)
    p_list.add_argument("--status", type=str)
    p_list.add_argument("--limit", type=int, default=50)
    
    p_seal = subparsers.add_parser("seal")
    p_seal.add_argument("batch_id", type=int)
    p_seal.add_argument("--yes", action="store_true")
    
    p_clear = subparsers.add_parser("clear")
    p_clear.add_argument("batch_id", type=int)
    p_clear.add_argument("--reason", required=True)
    p_clear.add_argument("--yes", action="store_true")
    
    args = parser.parse_args()
    
    if args.subcommand == "list":
        list_cmd(args)
    elif args.subcommand == "seal":
        seal_cmd(args)
    elif args.subcommand == "clear":
        clear_cmd(args)

if __name__ == "__main__":
    main()