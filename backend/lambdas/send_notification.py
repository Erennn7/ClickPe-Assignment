"""
AWS SES Notification Dispatcher
Formats personalized loan eligibility emails for matched users and dispatches
them safely via Amazon SES to verified test inboxes and email aliases.
"""

import os
import sys
import logging
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

sys.path.append(os.path.dirname(__file__))
from db_client import execute_sql

logger = logging.getLogger("notification")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def build_email_html(user_name: str, original_email: str, test_recipient: str, products: List[Dict[str, Any]]) -> str:
    """Render high-conversion responsive HTML email card."""
    products_html = ""
    for p in products:
        products_html += f"""
        <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 14px; background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
          <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
            <h3 style="margin: 0; color: #0f172a; font-size: 17px; font-weight: 700;">{p['product_name']}</h3>
            <span style="font-size: 13px; font-weight: 600; color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 4px;">{p['provider_name']}</span>
          </div>
          <p style="margin: 6px 0 2px; font-size: 14px; color: #334155;">
            <strong>Interest Rate:</strong> <span style="color: #059669; font-weight: bold; font-size: 15px;">{p['interest_rate']}%</span>
            &nbsp;•&nbsp; 
            <strong>Borrowing Power:</strong> <span style="font-weight: 600;">₹{int(p['max_eligible_loan']):,}</span>
          </p>
          <p style="margin: 8px 0 0; font-size: 13px; color: #64748b; line-height: 1.4; border-left: 2px solid #6366f1; padding-left: 10px;">
            {p['reasoning']}
          </p>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Pre-Approved Loan Offers</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
      <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); padding: 28px 24px; text-align: center;">
          <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;">ClickPe Loan Eligibility Engine</h1>
          <p style="color: #94a3b8; margin: 6px 0 0; font-size: 13px;">Automated Underwriting & Match Report</p>
        </div>
        <div style="padding: 24px;">
          <p style="font-size: 16px; color: #1e293b; margin: 0 0 12px;">Hello <strong>{user_name}</strong>,</p>
          <p style="font-size: 14px; color: #475569; line-height: 1.5; margin: 0 0 20px;">
            Congratulations! Based on your financial profile, our automated engine matched you with the following top personal loan products:
          </p>
          {products_html}
          <div style="margin-top: 24px; padding: 14px; background-color: #f8fafc; border-radius: 6px; font-size: 12px; color: #64748b; text-align: center;">
            🔒 <strong>Safety Notice:</strong> Test email delivered to <code>{test_recipient}</code> on behalf of CSV borrower <code>{original_email}</code>.
          </div>
        </div>
      </div>
    </body>
    </html>
    """


def dispatch_sample_notifications(limit_users: int = 2) -> int:
    """
    Fetches matches, groups them, and sends emails to the verified test address.
    """
    test_email = os.getenv("SES_TEST_RECIPIENT_EMAIL") or "samarthkolarkar+one@gmail.com"
    sender_email = os.getenv("SES_FROM_EMAIL") or "noreply@clickpe.com"
    region = os.getenv("AWS_REGION", "us-east-1")

    logger.info(f"Preparing notification dispatch for test inbox: {test_email}...")

    # Fetch top pending matches grouped by user
    sql = """
    SELECT 
      u.user_id, u.name, u.email,
      m.match_id, m.match_score, m.max_eligible_loan, m.reasoning,
      p.product_name, p.provider_name, p.interest_rate
    FROM matches m
    JOIN users u ON m.user_id = u.user_id
    JOIN loan_products p ON m.product_id = p.product_id
    WHERE m.notification_status = 'PENDING'
    ORDER BY u.user_id, m.match_score DESC
    LIMIT 20;
    """
    rows = execute_sql(sql, commit=False)

    if not rows:
        logger.info("No pending matches found to notify.")
        return 0

    user_map: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        uid = str(r["user_id"])
        if uid not in user_map:
            user_map[uid] = {
                "name": r["name"],
                "email": r["email"],
                "match_ids": [],
                "products": []
            }
        user_map[uid]["match_ids"].append(str(r["match_id"]))
        user_map[uid]["products"].append({
            "product_name": r["product_name"],
            "provider_name": r["provider_name"],
            "interest_rate": float(r["interest_rate"]),
            "max_eligible_loan": float(r["max_eligible_loan"]),
            "reasoning": r["reasoning"]
        })

    sent_count = 0
    os.makedirs("test_output", exist_ok=True)

    for i, (uid, data) in enumerate(list(user_map.items())[:limit_users]):
        # Use alias for multiple demo recipients: +one, +two
        alias_email = test_email if "+one" in test_email else test_email.replace("@", f"+{i+1}@")
        subject = f"🎉 Pre-Approved Loan Matches for {data['name']}"
        html_content = build_email_html(data["name"], data["email"], alias_email, data["products"])

        # Always save locally so it can be previewed/inspected in demo video
        preview_path = f"test_output/sample_email_user_{i+1}.html"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"\n📧 Generated Personalized Email for: {data['name']}")
        print(f"   • Recipient Alias: {alias_email}")
        print(f"   • Matched Loans: {len(data['products'])} offerings")
        print(f"   • Saved Local Preview: {preview_path}")

        # Attempt AWS SES Dispatch if AWS credentials configured
        aws_key = os.getenv("AWS_ACCESS_KEY_ID")
        if aws_key:
            try:
                ses = boto3.client("ses", region_name=region)
                resp = ses.send_email(
                    Source=sender_email,
                    Destination={"ToAddresses": [alias_email]},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Html": {"Data": html_content, "Charset": "UTF-8"}}
                    }
                )
                print(f"   ✅ Dispatched via AWS SES! MessageId: {resp.get('MessageId')}")
            except ClientError as e:
                print(f"   ⚠️  AWS SES notice (Sandbox/Verification): {e.response['Error']['Message']}")

        # Mark matches as NOTIFIED in DB
        execute_sql(
            "UPDATE matches SET notification_status = 'SENT' WHERE match_id = ANY(%s::uuid[]);",
            (data["match_ids"],)
        )
        sent_count += 1

    return sent_count


if __name__ == "__main__":
    count = dispatch_sample_notifications(limit_users=2)
    print(f"\n✅ Total notifications processed: {count}")
