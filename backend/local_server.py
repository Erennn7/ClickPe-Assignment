"""
Local Development & Testing Server
Bridges the Minimal Frontend UI with PostgreSQL, Lambda functions, and n8n workflows.
Supports both AWS S3 presigned uploads and 100% offline local file streaming.
"""

import os
import sys
import uuid
import time
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Add lambdas to path
sys.path.append(os.path.join(os.path.dirname(__file__), "lambdas"))
sys.path.append(os.path.join(os.path.dirname(__file__), "crawler"))

from lambdas.db_client import execute_sql
from lambdas.ingest_csv import process_csv_stream, notify_n8n_webhook
from lambdas.presigned_url import lambda_handler as presigned_lambda_handler
from crawler.scraper import run_crawler

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="The Loan Eligibility Engine",
    description="Event-driven loan eligibility and workflow automation pipeline",
    version="1.0.0"
)

# Enable CORS for local web interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """Health check for API and PostgreSQL database."""
    try:
        db_res = execute_sql("SELECT NOW() as now, COUNT(*) as product_count FROM loan_products;")
        return {
            "status": "HEALTHY",
            "database": "CONNECTED",
            "server_time": str(db_res[0]["now"]),
            "active_products": db_res[0]["product_count"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "UNHEALTHY", "error": str(e)})


@app.get("/api/presigned-url")
def get_presigned_url(filename: str = Query("users.csv")):
    """
    Generate an S3 Presigned PUT URL.
    Delegates to the exact AWS Lambda handler logic.
    """
    event = {"queryStringParameters": {"filename": filename}}
    resp = presigned_lambda_handler(event, None)
    return JSONResponse(status_code=resp["statusCode"], content=eval(resp["body"]))


@app.post("/api/upload-stream")
async def upload_stream(file: UploadFile = File(...)):
    """
    High-speed streaming ingestion endpoint for local offline testing.
    Streams CSV directly into PostgreSQL, tracks the batch, and triggers n8n.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    batch_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info(f"Received stream upload: {file.filename} (Batch ID: {batch_id})")

    # Record batch starting
    execute_sql(
        """
        INSERT INTO ingestion_batches (batch_id, filename, status, started_at)
        VALUES (%s, %s, 'PROCESSING', CURRENT_TIMESTAMP)
        """,
        (batch_id, file.filename)
    )

    # Stream file into PostgreSQL
    import io
    content = await file.read()
    text_stream = io.StringIO(content.decode("utf-8", errors="replace"))
    total_records = process_csv_stream(text_stream, batch_id)

    duration = time.time() - start_time

    # Update batch status
    execute_sql(
        """
        UPDATE ingestion_batches 
        SET status = 'COMPLETED', total_rows = %s, completed_at = CURRENT_TIMESTAMP 
        WHERE batch_id = %s
        """,
        (total_records, batch_id)
    )

    # Fire n8n webhook
    notify_n8n_webhook(batch_id, total_records, duration)

    return {
        "status": "SUCCESS",
        "batch_id": batch_id,
        "filename": file.filename,
        "total_records": total_records,
        "duration_seconds": round(duration, 2),
        "throughput_rows_per_sec": round(total_records / max(duration, 0.001), 0)
    }


@app.get("/api/stats")
def get_dashboard_stats():
    """Retrieve real-time metrics for UI dashboard cards."""
    try:
        users_count = execute_sql("SELECT COUNT(*) as count FROM users;")[0]["count"]
        products_count = execute_sql("SELECT COUNT(*) as count FROM loan_products WHERE is_active = TRUE;")[0]["count"]
        matches_count = execute_sql("SELECT COUNT(*) as count FROM matches;")[0]["count"]
        latest_batch = execute_sql("SELECT * FROM ingestion_batches ORDER BY started_at DESC LIMIT 1;")
        
        return {
            "total_users": users_count,
            "active_products": products_count,
            "total_matches": matches_count,
            "latest_batch": latest_batch[0] if latest_batch else None
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {"total_users": 0, "active_products": 0, "total_matches": 0, "latest_batch": None}


@app.get("/api/matches/sample")
def get_sample_matches(limit: int = 10):
    """Retrieve sample matched pairs for inspection in the UI."""
    sql = """
    SELECT m.match_id, m.match_score, m.max_eligible_loan, m.reasoning, m.notification_status,
           u.name as user_name, u.email as user_email, u.monthly_income, u.credit_score, u.employment_status,
           p.product_name, p.provider_name, p.interest_rate
    FROM matches m
    JOIN users u ON m.user_id = u.user_id
    JOIN loan_products p ON m.product_id = p.product_id
    ORDER BY m.created_at DESC
    LIMIT %s;
    """
    return execute_sql(sql, (limit,))


@app.post("/api/crawler/trigger")
def trigger_crawler_endpoint():
    """Manually trigger the loan discovery crawler."""
    count = run_crawler()
    return {"status": "SUCCESS", "products_updated": count}


# Serve Minimal Frontend Portal
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on http://localhost:{port}...")
    uvicorn.run("local_server:app", host="0.0.0.0", port=port, reload=True)
