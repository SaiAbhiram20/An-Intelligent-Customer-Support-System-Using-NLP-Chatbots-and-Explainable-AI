-- ═══════════════════════════════════════════════════════════════
-- Intelligent Customer Support System - Database Schema
-- PostgreSQL with UUID primary keys and automated timestamps
-- ═══════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── AUTO-UPDATE TIMESTAMP TRIGGER ───────────────────────────
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─── CUSTOMERS ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id     VARCHAR(20) UNIQUE NOT NULL,      -- CUST-001001
    email           VARCHAR(255) UNIQUE NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    phone           VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ─── SUBSCRIPTIONS ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id         VARCHAR(20) UNIQUE NOT NULL,  -- SUB-001001
    customer_id             UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    plan_name               VARCHAR(50) NOT NULL
                                CHECK (plan_name IN ('free','basic','pro','enterprise')),
    plan_price              DECIMAL(10,2) NOT NULL,
    billing_cycle           VARCHAR(20) DEFAULT 'monthly'
                                CHECK (billing_cycle IN ('monthly','annual')),
    status                  VARCHAR(20) DEFAULT 'active'
                                CHECK (status IN ('active','cancelled','expired','paused','trial')),
    start_date              DATE NOT NULL,
    current_period_start    DATE,
    current_period_end      DATE,
    auto_renew              BOOLEAN DEFAULT TRUE,
    cancelled_at            TIMESTAMPTZ,
    cancel_reason           TEXT,
    created_at              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER trg_subscriptions_updated
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ─── ORDERS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id                VARCHAR(20) UNIQUE NOT NULL,   -- ORD-100001
    customer_id             UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    status                  VARCHAR(30) DEFAULT 'processing'
                                CHECK (status IN ('processing','confirmed','shipped',
                                    'in_transit','out_for_delivery','delivered',
                                    'cancelled','returned','refunded')),
    subtotal                DECIMAL(10,2) NOT NULL,
    tax                     DECIMAL(10,2) DEFAULT 0,
    shipping_cost           DECIMAL(10,2) DEFAULT 0,
    total                   DECIMAL(10,2) NOT NULL,
    shipping_address_line1  VARCHAR(255),
    shipping_city           VARCHAR(100),
    shipping_state          VARCHAR(50),
    shipping_postal_code    VARCHAR(20),
    shipping_country        VARCHAR(100),
    tracking_number         VARCHAR(100),
    carrier                 VARCHAR(50),
    order_date              DATE NOT NULL DEFAULT CURRENT_DATE,
    shipped_date            DATE,
    estimated_delivery      DATE,
    actual_delivery         DATE,
    delivered_date          DATE,
    discount                DECIMAL(10,2) DEFAULT 0,
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER trg_orders_updated
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ─── ORDER ITEMS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_name    VARCHAR(255) NOT NULL,
    product_sku     VARCHAR(50),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      DECIMAL(10,2) NOT NULL,
    total_price     DECIMAL(10,2) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ─── TRANSACTIONS ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id      VARCHAR(20) UNIQUE NOT NULL,  -- TXN-200001
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_id            UUID REFERENCES orders(id),
    subscription_id     UUID REFERENCES subscriptions(id),
    type                VARCHAR(20) NOT NULL
                            CHECK (type IN ('charge','refund','subscription','adjustment')),
    status              VARCHAR(20) DEFAULT 'completed'
                            CHECK (status IN ('pending','completed','failed','refunded','disputed')),
    amount              DECIMAL(10,2) NOT NULL,
    currency            VARCHAR(10) DEFAULT 'USD',
    payment_method      VARCHAR(50),
    card_last_four      VARCHAR(4),
    card_brand          VARCHAR(50),
    refund_eligible     BOOLEAN DEFAULT TRUE,
    refund_deadline     DATE,
    refunded_amount     DECIMAL(10,2),
    refund_reason       TEXT,
    description         TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER trg_transactions_updated
    BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ─── INDEXES ─────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_order ON transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer ON subscriptions(customer_id);
