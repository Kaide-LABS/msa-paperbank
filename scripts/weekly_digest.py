import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from tabulate import tabulate
from app.db import SessionLocal, RequestLog, ImageBatch, Paper, PendingPaper
from app.config import settings
from app import pricing

def get_health_json():
    try:
        res = subprocess.run(["python", "-m", "admin.health"], capture_output=True, text=True)
        return json.loads(res.stdout)
    except Exception as e:
        return {"error": str(e)}

def run_digest(days: int, out_path: str | None):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    now = datetime.now(timezone.utc)
    
    with SessionLocal() as session:
        # 2. Activity
        total_reqs = session.execute(select(func.count(RequestLog.id)).where(RequestLog.received_at >= cutoff)).scalar() or 0
        distinct_phones = session.execute(select(func.count(func.distinct(RequestLog.wa_from))).where(RequestLog.received_at >= cutoff)).scalar() or 0
        
        outcomes = session.execute(
            select(RequestLog.outcome, func.count(RequestLog.id))
            .where(RequestLog.received_at >= cutoff)
            .group_by(RequestLog.outcome)
        ).all()
        outcome_map = {o: c for o, c in outcomes}
        
        # 3. Top Courses
        top_courses = session.execute(
            select(RequestLog.routed_course, func.count(RequestLog.id))
            .where(RequestLog.received_at >= cutoff, RequestLog.outcome == 'sent')
            .group_by(RequestLog.routed_course)
            .order_by(func.count(RequestLog.id).desc())
            .limit(10)
        ).all()
        
        # 4. Top Askers
        top_askers = session.execute(
            select(RequestLog.wa_from, func.count(RequestLog.id))
            .where(RequestLog.received_at >= cutoff)
            .group_by(RequestLog.wa_from)
            .order_by(func.count(RequestLog.id).desc())
            .limit(10)
        ).all()
        masked_askers = [[a[:-4] + "XXXX", c] for a, c in top_askers]
        
        # 5. Spend (Sum daily spend over the window - this is an approximation)
        # For a more accurate spend, we'd need a loop or a more complex query.
        # Let's just use the pricing estimate function for the entire window tokens.
        flash_in = session.execute(select(func.sum(RequestLog.flash_input_tokens)).where(RequestLog.received_at >= cutoff)).scalar() or 0
        flash_out = session.execute(select(func.sum(RequestLog.flash_output_tokens)).where(RequestLog.received_at >= cutoff)).scalar() or 0
        
        pro_batch_count = session.execute(
            select(func.count(ImageBatch.id))
            .where(ImageBatch.status == 'ocr_done', ImageBatch.sealed_at >= cutoff)
        ).scalar() or 0
        
        # We'll just report the totals.
        total_flash_usd = pricing.estimate_request_cost_usd(flash_in, flash_out)
        total_pro_usd = pro_batch_count * pricing.estimate_pro_cost_usd(5160, 500)
        total_usd = total_flash_usd + total_pro_usd # missing embeddings for brevity in digest
        
        # 6. Intake
        intake_stats = session.execute(
            select(ImageBatch.status, func.count(ImageBatch.id))
            .where(ImageBatch.opened_at >= cutoff)
            .group_by(ImageBatch.status)
        ).all()
        
        # 7. Library
        total_papers = session.execute(select(func.count(Paper.id)).where(Paper.is_retired == False)).scalar() or 0
        added_papers = session.execute(select(func.count(Paper.id)).where(Paper.uploaded_at >= cutoff)).scalar() or 0
        retired_papers = session.execute(select(func.count(Paper.id)).where(Paper.is_retired == True, Paper.retired_at >= cutoff)).scalar() or 0

    health = get_health_json()

    md = f"""# Weekly Digest: {cutoff.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}

## 1. Window
- **Start**: {cutoff.strftime('%Y-%m-%d %H:%M:%S')} UTC
- **End**: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC
- **Duration**: {days} days

## 2. Activity
- **Total Requests**: {total_reqs}
- **Distinct Users**: {distinct_phones}

### Outcomes Breakdown
{tabulate(outcomes, headers=["Outcome", "Count"], tablefmt="github")}

## 3. Top 10 Courses (Successful)
{tabulate(top_courses, headers=["Course", "Hits"], tablefmt="github")}

## 4. Top 10 Askers
{tabulate(masked_askers, headers=["Phone (masked)", "Requests"], tablefmt="github")}

## 5. Spend (Estimated)
- **Flash Tokens**: {flash_in:,} in / {flash_out:,} out
- **OCR Events**: {pro_batch_count}
- **Estimated USD**: ${total_usd:.4f}

## 6. Intake
{tabulate(intake_stats, headers=["Batch Status", "Count"], tablefmt="github")}

## 7. Library
- **Total Active Papers**: {total_papers}
- **Added in Window**: {added_papers}
- **Retired in Window**: {retired_papers}

## 8. Health
```json
{json.dumps(health, indent=2)}
```
"""

    if out_path:
        with open(out_path, "w") as f:
            f.write(md)
        print(f"Digest written to {out_path}")
    else:
        print(md)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()
    run_digest(args.days, args.out)
