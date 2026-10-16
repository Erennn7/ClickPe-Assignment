-- ==============================================================================
-- The Loan Eligibility Engine - PostgreSQL 16 Schema Definition
-- Optimized for high-throughput batch ingestion and indexed filtering
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Ingestion Batches: Tracks file uploads, counts, and processing lifecycle
CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    total_rows INT DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- 2. Users Table: Ingested borrower profiles
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY,
    batch_id UUID REFERENCES ingestion_batches(batch_id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    monthly_income NUMERIC(12, 2) NOT NULL,
    credit_score INT NOT NULL CHECK (credit_score BETWEEN 300 AND 900),
    employment_status VARCHAR(50) NOT NULL,
    age INT NOT NULL CHECK (age BETWEEN 18 AND 100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Loan Products Table: Autonomous discoveries from web crawlers & partners
CREATE TABLE IF NOT EXISTS loan_products (
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_name VARCHAR(255) NOT NULL,
    provider_name VARCHAR(255) NOT NULL,
    interest_rate NUMERIC(5, 2) NOT NULL,
    min_income NUMERIC(12, 2) NOT NULL DEFAULT 15000,
    min_credit_score INT NOT NULL DEFAULT 650,
    min_age INT NOT NULL DEFAULT 21,
    max_age INT NOT NULL DEFAULT 60,
    eligible_employment_status TEXT[] NOT NULL DEFAULT '{"Salaried", "Self-Employed", "Business"}',
    max_loan_amount NUMERIC(14, 2) DEFAULT 4000000,
    processing_fee VARCHAR(100) DEFAULT '1.0% - 2.5%',
    features TEXT,
    source_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_product_provider UNIQUE (product_name, provider_name)
);

-- 4. Matches Table: Filtered and evaluated user-loan pairings
CREATE TABLE IF NOT EXISTS matches (
    match_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES loan_products(product_id) ON DELETE CASCADE,
    batch_id UUID REFERENCES ingestion_batches(batch_id) ON DELETE SET NULL,
    match_score NUMERIC(5, 2) NOT NULL,
    max_eligible_loan NUMERIC(14, 2),
    reasoning TEXT,
    notification_status VARCHAR(50) DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_product_batch UNIQUE (user_id, product_id, batch_id)
);

-- ==============================================================================
-- HIGH-PERFORMANCE INDEXES
-- Critical for Stage 1 of The Optimization Treasure Hunt
-- ==============================================================================

-- Index for querying users by batch
CREATE INDEX IF NOT EXISTS idx_users_batch_id ON users (batch_id);

-- Composite Index on users for the Stage 1 push-down hard filter
CREATE INDEX IF NOT EXISTS idx_users_eligibility ON users (credit_score, monthly_income, age, employment_status);

-- Product lookup index for range evaluation
CREATE INDEX IF NOT EXISTS idx_loan_products_criteria ON loan_products (min_credit_score, min_income, min_age, max_age);

-- Index for fetching pending notifications in Workflow C
CREATE INDEX IF NOT EXISTS idx_matches_batch_status ON matches (batch_id, notification_status);
CREATE INDEX IF NOT EXISTS idx_matches_user_id ON matches (user_id);
