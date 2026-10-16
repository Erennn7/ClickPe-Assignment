-- ==============================================================================
-- The Loan Eligibility Engine - Seed Loan Products
-- Realistic baseline personal loan offerings across major Indian institutions
-- ==============================================================================

INSERT INTO loan_products (
    product_name, provider_name, interest_rate, min_income, min_credit_score, min_age, max_age, 
    eligible_employment_status, max_loan_amount, processing_fee, features, source_url
) VALUES
(
    'HDFC Insta Personal Loan', 
    'HDFC Bank', 
    10.50, 
    25000, 
    720, 
    21, 
    60, 
    '{"Salaried"}', 
    4000000, 
    '1.25%', 
    'Instant disbursal in 10 seconds for pre-approved customers; Zero paperwork; Flexible tenure 12-60 months.',
    'https://www.hdfcbank.com/personal/borrow/popular-loans/personal-loan'
),
(
    'ICICI Pru-Credit Personal Loan', 
    'ICICI Bank', 
    10.75, 
    30000, 
    700, 
    23, 
    58, 
    '{"Salaried", "Self-Employed"}', 
    5000000, 
    '1.50%', 
    'Competitive interest rates; 100% digital sanction; Special benefits for doctors and chartered accountants.',
    'https://www.icicibank.com/personal-banking/loans/personal-loan'
),
(
    'SBI Xpress Credit', 
    'State Bank of India', 
    11.15, 
    15000, 
    680, 
    21, 
    58, 
    '{"Salaried", "Business"}', 
    3000000, 
    '1.00%', 
    'Low processing fee; Daily reducing balance method; No hidden charges; Special concessions for government employees.',
    'https://sbi.co.in/web/personal-banking/loans/personal-loans/xpress-credit-personal-loan'
),
(
    'Axis Bank Prime Personal Loan', 
    'Axis Bank', 
    10.49, 
    40000, 
    750, 
    21, 
    60, 
    '{"Salaried", "Self-Employed"}', 
    4000000, 
    '1.00%', 
    'Lowest interest rates for prime credit profiles; Flexible repayment from 12 to 84 months; Quick online approval.',
    'https://www.axisbank.com/retail/loans/personal-loan'
),
(
    'Bajaj Finserv Flexi Hybrid Loan', 
    'Bajaj Finserv', 
    12.25, 
    22000, 
    675, 
    21, 
    65, 
    '{"Salaried", "Self-Employed", "Business"}', 
    3500000, 
    '2.00%', 
    'Withdraw money as you need it and prepay anytime without extra charges; Interest charged only on utilized amount.',
    'https://www.bajajfinserv.in/personal-loan'
),
(
    'Tata Capital Growth Personal Loan', 
    'Tata Capital', 
    11.99, 
    35000, 
    700, 
    22, 
    58, 
    '{"Self-Employed", "Business"}', 
    2500000, 
    '1.75%', 
    'Customized loans for SME business owners and consultants; Minimal income proof documentation; Zero collateral.',
    'https://www.tatacapital.com/personal-loan.html'
),
(
    'Kotak Mahindra Smart Personal Loan', 
    'Kotak Mahindra Bank', 
    10.99, 
    28000, 
    710, 
    21, 
    60, 
    '{"Salaried"}', 
    3000000, 
    '1.50%', 
    'Disbursal in under 3 seconds with Kotak Net Banking; Attractive part-prepayment facilities after 12 months.',
    'https://www.kotak.com/en/personal-banking/loans/personal-loan.html'
),
(
    'IDFC FIRST Bank FIRST Power Loan', 
    'IDFC FIRST Bank', 
    10.75, 
    20000, 
    690, 
    21, 
    60, 
    '{"Salaried", "Self-Employed", "Business"}', 
    2000000, 
    '1.00%', 
    'Zero foreclosure charges after 3 EMIs; No physical documentation; Completely paperless digital KYC.',
    'https://www.idfcfirstbank.com/personal-banking/loans/personal-loan'
)
ON CONFLICT (product_name, provider_name) DO UPDATE SET
    interest_rate = EXCLUDED.interest_rate,
    min_income = EXCLUDED.min_income,
    min_credit_score = EXCLUDED.min_credit_score,
    min_age = EXCLUDED.min_age,
    max_age = EXCLUDED.max_age,
    eligible_employment_status = EXCLUDED.eligible_employment_status,
    features = EXCLUDED.features,
    updated_at = CURRENT_TIMESTAMP;
