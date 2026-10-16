"""
AWS Lambda Handler: Streaming CSV Ingestion Engine
Handles s3:ObjectCreated events, streams 10,000+ rows directly to PostgreSQL via batch COPY,
and notifies the n8n Matching Engine via Webhook.
"""

import os
import sys
import io
import csv
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
import boto3
import requests

# Ensure local imports work when invoked from any directory
sys.path.append(os.path.dirname(__file__))
from db_client import bulk_insert_rows, execute_sql

logger = logging.getLogger("ingest_csv")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def notify_n8n_webhook(batch_id: str, total_count: int, duration_sec: float) -> bool:
    """
    Fire webhook event to n8n Workflow B (User-Loan Matching Engine).
    """
    webhook_url = os.getenv(
        "N8N_MATCHING_WEBHOOK_URL", 
        "http://localhost:5678/webhook/matching-trigger"
    )
    
    payload = {
        "event": "USER_INGESTION_COMPLETED",
        "batch_id": batch_id,
        "total_users": total_count,
        "duration_seconds": round(duration_sec, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    try:
        logger.info(f"Triggering n8n matching webhook at {webhook_url}...")
        resp = requests.post(webhook_url, json=payload, timeout=5)
        logger.info(f"n8n webhook responded with status {resp.status_code}")
        return resp.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"Could not reach n8n webhook (workflow may not be active yet): {e}")
        return False


def process_csv_stream(stream, batch_id: str, chunk_size: int = 1000) -> int:
    """
    Reads CSV line-by-line from a text stream, batching records into PostgreSQL.
    Memory footprint remains O(chunk_size) even for gigabyte-scale CSVs.
    """
    reader = csv.DictReader(stream)
    columns = [
        "user_id", "batch_id", "name", "email", 
        "monthly_income", "credit_score", "employment_status", "age"
    ]

    rows_buffer: List[Tuple[Any, ...]] = []
    total_processed = 0

    for row in reader:
        try:
            user_id = row.get("user_id") or str(uuid.uuid4())
            name = row.get("name", "Unknown").strip()
            email = row.get("email", "").strip()
            monthly_income = float(row.get("monthly_income", 0))
            credit_score = int(row.get("credit_score", 650))
            employment_status = row.get("employment_status", "Salaried").strip()
            age = int(row.get("age", 30))

            rows_buffer.append((
                user_id, batch_id, name, email,
                monthly_income, credit_score, employment_status, age
            ))

            if len(rows_buffer) >= chunk_size:
                bulk_insert_rows("users", columns, rows_buffer, page_size=chunk_size)
                total_processed += len(rows_buffer)
                rows_buffer.clear()
                logger.info(f"Ingested {total_processed} rows...")

        except Exception as row_err:
            logger.warning(f"Skipping malformed row: {row} - Error: {row_err}")

    # Flush remainder
    if rows_buffer:
        bulk_insert_rows("users", columns, rows_buffer, page_size=chunk_size)
        total_processed += len(rows_buffer)
        rows_buffer.clear()

    return total_processed


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entry point for S3 ObjectCreated events.
    """
    start_time = time.time()
    logger.info(f"Received event: {json.dumps(event)[:300]}...")

    records = event.get("Records", [])
    if not records:
        logger.warning("No S3 records found in event.")
        return {"statusCode": 400, "body": "No S3 event records"}

    s3_client = boto3.client("s3")
    total_all_records = 0

    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info(f"Processing object s3://{bucket}/{key}")

        parts = key.split("/")
        batch_id = parts[1] if len(parts) >= 3 and len(parts[1]) == 36 else str(uuid.uuid4())

        try:
            execute_sql(
                """
                INSERT INTO ingestion_batches (batch_id, filename, status, started_at)
                VALUES (%s, %s, 'PROCESSING', CURRENT_TIMESTAMP)
                ON CONFLICT (batch_id) DO UPDATE SET status = 'PROCESSING';
                """,
                (batch_id, os.path.basename(key))
            )
        except Exception as e:
            logger.warning(f"Batch tracking error: {e}")

        s3_obj = s3_client.get_object(Bucket=bucket, Key=key)
        stream = io.TextIOWrapper(s3_obj["Body"], encoding="utf-8", errors="replace")

        total_records = process_csv_stream(stream, batch_id)
        total_all_records += total_records

        duration = time.time() - start_time

        execute_sql(
            """
            UPDATE ingestion_batches
            SET status = 'COMPLETED', total_rows = %s, completed_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s;
            """,
            (total_records, batch_id)
        )

        logger.info(f"Successfully ingested {total_records} records for batch {batch_id} in {duration:.2f}s")
        notify_n8n_webhook(batch_id, total_records, duration)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Ingestion completed successfully",
            "total_records": total_all_records,
            "duration_seconds": round(time.time() - start_time, 2)
        })
    }


def run_local_ingest(file_path: str, batch_id: Optional[str] = None):
    """
    Helper for local testing directly from filesystem without AWS.
    """
    start_time = time.time()
    batch_id = batch_id or str(uuid.uuid4())
    filename = os.path.basename(file_path)

    print(f"\n🚀 Running local CSV ingestion for '{filename}' (Batch ID: {batch_id})...")

    execute_sql(
        """
        INSERT INTO ingestion_batches (batch_id, filename, status, started_at)
        VALUES (%s, %s, 'PROCESSING', CURRENT_TIMESTAMP)
        ON CONFLICT (batch_id) DO UPDATE SET status = 'PROCESSING';
        """,
        (batch_id, filename)
    )

    with open(file_path, "r", encoding="utf-8") as f:
        total = process_csv_stream(f, batch_id)

    duration = time.time() - start_time
    execute_sql(
        """
        UPDATE ingestion_batches
        SET status = 'COMPLETED', total_rows = %s, completed_at = CURRENT_TIMESTAMP
        WHERE batch_id = %s;
        """,
        (total, batch_id)
    )

    throughput = total / max(duration, 0.001)
    print(f"✅ Ingestion finished: {total} records ingested in {duration:.2f} seconds ({throughput:.0f} rows/sec)!")
    notify_n8n_webhook(batch_id, total, duration)
    return batch_id, total


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "sample_data/users.csv"
    run_local_ingest(csv_file)
