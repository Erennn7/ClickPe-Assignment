"""
End-to-End Matching Pipeline Runner
Executes The Optimization Treasure Hunt (3-Stage Funnel) directly against PostgreSQL
and generates matches for the notification engine.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, List

# Add lambdas to path
sys.path.append(os.path.join(os.path.dirname(__file__), "lambdas"))
from db_client import execute_sql, bulk_insert_rows

logger = logging.getLogger("matching_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_matching_engine(batch_id: str = None) -> int:
    """
    Executes the 3-Stage Optimization Funnel:
    1. Stage 1: Fast SQL Hard Filter via B-Tree Index Push-down
    2. Stage 2: In-Memory Heuristic Scoring & Top-K per user
    3. Stage 3: Qualitative Underwriting Reasoning & Batch Persistence
    """
    print("=" * 70)
    print("🎯 CLICKPE LOAN ELIGIBILITY ENGINE: THE OPTIMIZATION TREASURE HUNT")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # STAGE 1: SQL HARD FILTER (Database Engine Push-down)
    # -------------------------------------------------------------------------
    stage1_start = time.time()
    logger.info("Executing Stage 1: Indexed SQL Push-down filter in PostgreSQL...")

    stage1_sql = """
    SELECT 
      u.user_id, u.batch_id, u.name, u.email, u.monthly_income, u.credit_score, u.age, u.employment_status,
      p.product_id, p.product_name, p.provider_name, p.interest_rate, p.min_income, p.min_credit_score,
      p.max_loan_amount
    FROM users u
    JOIN loan_products p 
      ON  u.credit_score >= p.min_credit_score
      AND u.monthly_income >= p.min_income
      AND u.age BETWEEN p.min_age AND p.max_age
      AND (p.eligible_employment_status IS NULL OR u.employment_status = ANY(p.eligible_employment_status))
    WHERE p.is_active = TRUE
    """
    params = ()
    if batch_id:
        stage1_sql += " AND u.batch_id = %s"
        params = (batch_id,)

    candidates = execute_sql(stage1_sql, params, commit=False)
    stage1_duration = time.time() - stage1_start

    print(f"\n📊 STAGE 1 BENCHMARK (SQL Push-down):")
    print(f"  • Candidate Pairs Matched: {len(candidates):,} pairs")
    print(f"  • Time Taken: {stage1_duration*1000:.2f} ms")
    print(f"  • LLM Tokens Spent: 0 (Cost: $0.00)")
    print(f"  • Evaluation Strategy: PostgreSQL B-Tree Index Bitmap Scan")

    # -------------------------------------------------------------------------
    # STAGE 2: HEURISTIC SCORING & TOP-K RANKING (In-Memory Math)
    # -------------------------------------------------------------------------
    stage2_start = time.time()
    user_map: Dict[str, List[Dict[str, Any]]] = {}

    for row in candidates:
        uid = str(row["user_id"])
        income = float(row["monthly_income"])
        credit = int(row["credit_score"])
        rate = float(row["interest_rate"])
        min_income = float(row["min_income"])
        min_credit = int(row["min_credit_score"])

        # FOIR 50% Cap -> Maximum Eligible Loan
        max_emi = income * 0.50
        max_loan = min(float(row["max_loan_amount"] or 4000000), round(max_emi * 36))

        # Suitability Score Formula (0 - 100)
        rate_score = max(0, (15 - rate) * 10)
        income_surplus = min(30, ((income - min_income) / min_income) * 20)
        credit_bonus = min(25, ((credit - min_credit) / 5))
        total_score = round(min(99.9, rate_score * 0.45 + income_surplus + credit_bonus), 1)

        candidate = {
            **row,
            "match_score": total_score,
            "max_eligible_loan": max_loan
        }

        if uid not in user_map:
            user_map[uid] = []
        user_map[uid].append(candidate)

    # Rank and pick Top 3 per user
    top_matches = []
    for uid, offers in user_map.items():
        offers.sort(key=lambda x: x["match_score"], reverse=True)
        top_matches.extend(offers[:3])

    stage2_duration = time.time() - stage2_start

    print(f"\n⚡ STAGE 2 BENCHMARK (Heuristic Scoring & Top-K):")
    print(f"  • Total Qualified Users: {len(user_map):,} borrowers")
    print(f"  • Candidate Matches Filtered to Top 3: {len(top_matches):,} prime matches")
    print(f"  • Time Taken: {stage2_duration*1000:.2f} ms")
    print(f"  • Reduction from Stage 1: {((1 - len(top_matches)/max(len(candidates), 1))*100):.1f}%")

    # -------------------------------------------------------------------------
    # STAGE 3: QUALITATIVE UNDERWRITING REASONING & PERSISTENCE
    # -------------------------------------------------------------------------
    stage3_start = time.time()
    
    match_rows_to_insert = []
    for m in top_matches:
        tier = "Prime" if m["credit_score"] >= 750 else "Near-Prime" if m["credit_score"] >= 700 else "Standard"
        reasoning = (
            f"Pre-approved based on {m['employment_status']} status and {tier} credit rating ({m['credit_score']}). "
            f"Qualifies for {m['provider_name']}'s preferred {m['interest_rate']}% rate with eligible borrowing up to "
            f"₹{int(m['max_eligible_loan']):,}."
        )

        match_rows_to_insert.append((
            str(m["user_id"]),
            str(m["product_id"]),
            str(m["batch_id"]) if m.get("batch_id") else None,
            m["match_score"],
            m["max_eligible_loan"],
            reasoning,
            "PENDING"
        ))

    # Bulk insert matches using execute_values
    columns = [
        "user_id", "product_id", "batch_id", "match_score", 
        "max_eligible_loan", "reasoning", "notification_status"
    ]
    
    # Insert in chunks
    inserted = bulk_insert_rows("matches", columns, match_rows_to_insert, page_size=2000)
    stage3_duration = time.time() - stage3_start

    print(f"\n📝 STAGE 3 BENCHMARK (Qualitative Reasoning & DB Write):")
    print(f"  • Matches Stored in PostgreSQL: {len(match_rows_to_insert):,}")
    print(f"  • Time Taken: {stage3_duration*1000:.2f} ms")
    print(f"  • Status: Flagged PENDING for AWS SES Notification (Workflow C)")

    total_pipeline_time = stage1_duration + stage2_duration + stage3_duration
    print("\n" + "=" * 70)
    print(f"🚀 TOTAL 3-STAGE FUNNEL EXECUTION TIME: {total_pipeline_time:.2f} seconds")
    print(f"   Throughput: {len(candidates)/total_pipeline_time:,.0f} user-product evaluations/sec")
    print("=" * 70)

    return len(match_rows_to_insert)


if __name__ == "__main__":
    count = run_matching_engine()
