"""
AWS Lambda Handler: S3 Presigned URL Generator
Enables secure, scalable direct-to-S3 CSV uploads bypassing API Gateway size/timeout limits.
"""

import os
import sys
import json
import uuid
import logging
from typing import Dict, Any
import boto3
from botocore.config import Config

sys.path.append(os.path.dirname(__file__))
from db_client import execute_sql

logger = logging.getLogger("presigned_url")
logger.setLevel(logging.INFO)

# CORS headers for browser requests
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json"
}


def get_s3_client():
    """Create S3 client configured for signature version 4."""
    region = os.getenv("AWS_REGION", "us-east-1")
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(signature_version="s3v4")
    )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    HTTP Handler: Generates S3 Presigned PUT URL and registers ingestion batch.
    """
    try:
        # Handle OPTIONS preflight
        http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
        if http_method == "OPTIONS":
            return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"ok": True})}

        # Extract filename from query params or body
        params = event.get("queryStringParameters") or {}
        if not params and event.get("body"):
            try:
                body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
                params = body
            except Exception:
                pass

        filename = params.get("filename", "users.csv")
        if not filename.lower().endswith(".csv"):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Only CSV files (.csv) are allowed for bulk user ingestion."})
            }

        bucket_name = os.getenv("S3_BUCKET_NAME", "clickpe-loan-engine-user-uploads")
        batch_id = str(uuid.uuid4())
        file_key = f"uploads/{batch_id}/{filename}"
        expires_in = int(os.getenv("PRESIGNED_URL_EXPIRES_IN", "3600"))

        # Register pending batch in PostgreSQL database
        try:
            execute_sql(
                "INSERT INTO ingestion_batches (batch_id, filename, status) VALUES (%s, %s, 'PENDING')",
                (batch_id, filename)
            )
            logger.info(f"Registered batch {batch_id} in database.")
        except Exception as db_err:
            logger.warning(f"Failed to record batch in DB (non-fatal for URL generation): {db_err}")

        # Generate presigned PUT URL
        s3_client = get_s3_client()
        upload_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket_name,
                "Key": file_key,
                "ContentType": "text/csv"
            },
            ExpiresIn=expires_in
        )

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "batch_id": batch_id,
                "file_key": file_key,
                "upload_url": upload_url,
                "bucket": bucket_name,
                "expires_in": expires_in
            })
        }

    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }


if __name__ == "__main__":
    # Local CLI test run
    print("Testing presigned URL generation locally...")
    response = lambda_handler({"queryStringParameters": {"filename": "users_sample.csv"}}, None)
    print("Response Status:", response["statusCode"])
    print("Response Body:", response["body"])
