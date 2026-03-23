-- ═══════════════════════════════════════════════════════════════
-- Sample Data - Realistic Test Scenarios
-- ═══════════════════════════════════════════════════════════════

-- ─── CUSTOMERS ───────────────────────────────────────────────

INSERT INTO customers (customer_id, email, first_name, last_name, phone, status)
VALUES
    ('CUST-001001', 'sarah.johnson@email.com',  'Sarah',  'Johnson', '+1-415-555-0101', 'active'),
    ('CUST-001002', 'mike.chen@email.com',      'Mike',   'Chen',    '+1-310-555-0102', 'active'),
    ('CUST-001003', 'emily.davis@email.com',     'Emily',  'Davis',   '+1-312-555-0103', 'active'),
    ('CUST-001004', 'david.wilson@email.com',    'David',  'Wilson',  '+1-212-555-0104', 'active'),
    ('CUST-001005', 'lisa.martinez@email.com',   'Lisa',   'Martinez','+1-305-555-0105', 'active'),
    ('CUST-001006', 'james.brown@email.com',     'James',  'Brown',   '+1-206-555-0106', 'active')
ON CONFLICT (customer_id) DO NOTHING;

-- ─── SUBSCRIPTIONS ───────────────────────────────────────────

INSERT INTO subscriptions (subscription_id, customer_id, plan_name, plan_price, billing_cycle, status, start_date, current_period_start, current_period_end, auto_renew)
SELECT 'SUB-001001', id, 'pro',        29.99,  'monthly', 'active',    '2025-06-01', '2026-02-01', '2026-03-01', TRUE  FROM customers WHERE customer_id='CUST-001001'
UNION ALL
SELECT 'SUB-001002', id, 'basic',      9.99,   'monthly', 'active',    '2025-09-15', '2026-02-15', '2026-03-15', TRUE  FROM customers WHERE customer_id='CUST-001002'
UNION ALL
SELECT 'SUB-001003', id, 'pro',        29.99,  'monthly', 'cancelled', '2025-03-01', '2026-01-01', '2026-02-01', FALSE FROM customers WHERE customer_id='CUST-001003'
UNION ALL
SELECT 'SUB-001004', id, 'enterprise', 99.99,  'annual',  'active',    '2025-01-01', '2025-01-01', '2026-01-01', TRUE  FROM customers WHERE customer_id='CUST-001004'
UNION ALL
SELECT 'SUB-001005', id, 'free',       0.00,   'monthly', 'active',    '2025-11-01', '2026-02-01', '2026-03-01', TRUE  FROM customers WHERE customer_id='CUST-001005'
UNION ALL
SELECT 'SUB-001006', id, 'basic',      9.99,   'monthly', 'paused',    '2025-07-01', '2026-01-01', '2026-02-01', FALSE FROM customers WHERE customer_id='CUST-001006'
ON CONFLICT (subscription_id) DO NOTHING;

-- ─── ORDERS ──────────────────────────────────────────────────

-- Sarah: Delivered order (happy customer)
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    tracking_number, carrier, order_date, shipped_date, estimated_delivery, actual_delivery, delivered_date)
SELECT 'ORD-100001', id, 'delivered', 149.99, 12.00, 0.00, 161.99,
    '123 Main Street', 'San Francisco', 'CA', '94102',
    '1Z999AA10123456784', 'UPS', '2026-01-10', '2026-01-12', '2026-01-20', '2026-01-19', '2026-01-19'
FROM customers WHERE customer_id='CUST-001001'
ON CONFLICT (order_id) DO NOTHING;

-- Mike: Delivered order, wants refund (within 30-day window)
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    tracking_number, carrier, order_date, shipped_date, actual_delivery, delivered_date)
SELECT 'ORD-100002', id, 'delivered', 79.99, 6.40, 5.99, 92.38,
    '456 Oak Avenue', 'Los Angeles', 'CA', '90001',
    '9400111899223456789012', 'USPS', '2026-01-20', '2026-01-22', '2026-01-28', '2026-01-28'
FROM customers WHERE customer_id='CUST-001002'
ON CONFLICT (order_id) DO NOTHING;

-- Emily: In-transit order, delayed
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    tracking_number, carrier, order_date, shipped_date, estimated_delivery, notes)
SELECT 'ORD-100003', id, 'in_transit', 199.99, 16.00, 0.00, 215.99,
    '789 Pine Road', 'Chicago', 'IL', '60601',
    '794644790132', 'FedEx', '2026-02-01', '2026-02-03', '2026-02-10',
    'Weather delay in midwest distribution center'
FROM customers WHERE customer_id='CUST-001003'
ON CONFLICT (order_id) DO NOTHING;

-- David: Multiple orders - one processing, one delivered
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    order_date)
SELECT 'ORD-100004', id, 'processing', 349.99, 28.00, 0.00, 377.99,
    '321 Broadway', 'New York', 'NY', '10001', '2026-02-15'
FROM customers WHERE customer_id='CUST-001004'
ON CONFLICT (order_id) DO NOTHING;

INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    tracking_number, carrier, order_date, shipped_date, actual_delivery, delivered_date)
SELECT 'ORD-100005', id, 'delivered', 59.99, 4.80, 5.99, 70.78,
    '321 Broadway', 'New York', 'NY', '10001',
    '1Z999BB20987654321', 'UPS', '2025-12-01', '2025-12-03', '2025-12-08', '2025-12-08'
FROM customers WHERE customer_id='CUST-001004'
ON CONFLICT (order_id) DO NOTHING;

-- Lisa: Cancelled order
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    order_date, notes)
SELECT 'ORD-100006', id, 'cancelled', 129.99, 10.40, 7.99, 148.38,
    '555 Ocean Drive', 'Miami', 'FL', '33139', '2026-02-05',
    'Customer requested cancellation before shipment'
FROM customers WHERE customer_id='CUST-001005'
ON CONFLICT (order_id) DO NOTHING;

-- James: Returned order (outside refund window)
INSERT INTO orders (order_id, customer_id, status, subtotal, tax, shipping_cost, total,
    shipping_address_line1, shipping_city, shipping_state, shipping_postal_code,
    tracking_number, carrier, order_date, shipped_date, actual_delivery, delivered_date)
SELECT 'ORD-100007', id, 'returned', 249.99, 20.00, 0.00, 269.99,
    '100 Pike Street', 'Seattle', 'WA', '98101',
    '9261290100130435082807', 'USPS', '2025-10-01', '2025-10-03', '2025-10-08', '2025-10-08'
FROM customers WHERE customer_id='CUST-001006'
ON CONFLICT (order_id) DO NOTHING;

-- ─── ORDER ITEMS ─────────────────────────────────────────────

-- ORD-100001 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Wireless Noise-Canceling Headphones', 'WH-1000XM5', 1, 149.99, 149.99
FROM orders WHERE order_id='ORD-100001'
ON CONFLICT DO NOTHING;

-- ORD-100002 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Smart LED Desk Lamp', 'LED-DESK-01', 1, 49.99, 49.99
FROM orders WHERE order_id='ORD-100002'
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'USB-C Hub Adapter', 'USB-HUB-7P', 1, 30.00, 30.00
FROM orders WHERE order_id='ORD-100002'
ON CONFLICT DO NOTHING;

-- ORD-100003 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Mechanical Keyboard RGB', 'KB-MECH-RGB', 1, 129.99, 129.99
FROM orders WHERE order_id='ORD-100003'
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Ergonomic Mouse Pad XL', 'MP-ERGO-XL', 2, 35.00, 70.00
FROM orders WHERE order_id='ORD-100003'
ON CONFLICT DO NOTHING;

-- ORD-100004 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, '4K Ultra Monitor 27"', 'MON-4K-27', 1, 349.99, 349.99
FROM orders WHERE order_id='ORD-100004'
ON CONFLICT DO NOTHING;

-- ORD-100005 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Bluetooth Speaker Portable', 'SPK-BT-01', 1, 59.99, 59.99
FROM orders WHERE order_id='ORD-100005'
ON CONFLICT DO NOTHING;

-- ORD-100006 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Smart Fitness Watch', 'FIT-WATCH-02', 1, 129.99, 129.99
FROM orders WHERE order_id='ORD-100006'
ON CONFLICT DO NOTHING;

-- ORD-100007 items
INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Wireless Earbuds Pro', 'EAR-PRO-01', 1, 199.99, 199.99
FROM orders WHERE order_id='ORD-100007'
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_name, product_sku, quantity, unit_price, total_price)
SELECT id, 'Charging Case', 'EAR-CASE-01', 1, 50.00, 50.00
FROM orders WHERE order_id='ORD-100007'
ON CONFLICT DO NOTHING;

-- ─── TRANSACTIONS ────────────────────────────────────────────

-- Sarah: Completed charge
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200001', c.id, o.id, 'charge', 'completed', 161.99, 'Visa ending 4242', TRUE, '2026-02-19', 'Payment for order ORD-100001', '2026-01-10'
FROM customers c JOIN orders o ON o.order_id='ORD-100001' WHERE c.customer_id='CUST-001001'
ON CONFLICT (transaction_id) DO NOTHING;

-- Mike: Charge (refund eligible - within 30 days)
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200002', c.id, o.id, 'charge', 'completed', 92.38, 'Mastercard ending 5555', TRUE, '2026-02-28', 'Payment for order ORD-100002', '2026-01-20'
FROM customers c JOIN orders o ON o.order_id='ORD-100002' WHERE c.customer_id='CUST-001002'
ON CONFLICT (transaction_id) DO NOTHING;

-- Emily: Charge for in-transit order
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200003', c.id, o.id, 'charge', 'completed', 215.99, 'Visa ending 1234', TRUE, '2026-03-01', 'Payment for order ORD-100003', '2026-02-01'
FROM customers c JOIN orders o ON o.order_id='ORD-100003' WHERE c.customer_id='CUST-001003'
ON CONFLICT (transaction_id) DO NOTHING;

-- David: Two charges
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200004', c.id, o.id, 'charge', 'completed', 377.99, 'Amex ending 3782', TRUE, '2026-03-15', 'Payment for order ORD-100004', '2026-02-15'
FROM customers c JOIN orders o ON o.order_id='ORD-100004' WHERE c.customer_id='CUST-001004'
ON CONFLICT (transaction_id) DO NOTHING;

INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200005', c.id, o.id, 'charge', 'completed', 70.78, 'Amex ending 3782', FALSE, '2025-12-31', 'Payment for order ORD-100005', '2025-12-01'
FROM customers c JOIN orders o ON o.order_id='ORD-100005' WHERE c.customer_id='CUST-001004'
ON CONFLICT (transaction_id) DO NOTHING;

-- Lisa: Refunded cancelled order
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, description, transaction_date)
SELECT 'TXN-200006', c.id, o.id, 'charge', 'refunded', 148.38, 'Visa ending 9876', FALSE, 'Payment for order ORD-100006 (refunded)', '2026-02-05'
FROM customers c JOIN orders o ON o.order_id='ORD-100006' WHERE c.customer_id='CUST-001005'
ON CONFLICT (transaction_id) DO NOTHING;

INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, description, transaction_date)
SELECT 'TXN-200007', c.id, o.id, 'refund', 'completed', 148.38, 'Visa ending 9876', 'Refund for cancelled order ORD-100006', '2026-02-06'
FROM customers c JOIN orders o ON o.order_id='ORD-100006' WHERE c.customer_id='CUST-001005'
ON CONFLICT (transaction_id) DO NOTHING;

-- James: Old order charge (outside refund window)
INSERT INTO transactions (transaction_id, customer_id, order_id, type, status, amount, payment_method, refund_eligible, refund_deadline, description, transaction_date)
SELECT 'TXN-200008', c.id, o.id, 'charge', 'completed', 269.99, 'Discover ending 6011', FALSE, '2025-11-01', 'Payment for order ORD-100007', '2025-10-01'
FROM customers c JOIN orders o ON o.order_id='ORD-100007' WHERE c.customer_id='CUST-001006'
ON CONFLICT (transaction_id) DO NOTHING;

-- Subscription charges
INSERT INTO transactions (transaction_id, customer_id, subscription_id, type, status, amount, payment_method, description, transaction_date)
SELECT 'TXN-300001', c.id, s.id, 'subscription', 'completed', 29.99, 'Visa ending 4242', 'Monthly Pro subscription', '2026-02-01'
FROM customers c JOIN subscriptions s ON s.subscription_id='SUB-001001' WHERE c.customer_id='CUST-001001'
ON CONFLICT (transaction_id) DO NOTHING;

INSERT INTO transactions (transaction_id, customer_id, subscription_id, type, status, amount, payment_method, description, transaction_date)
SELECT 'TXN-300002', c.id, s.id, 'subscription', 'completed', 9.99, 'Mastercard ending 5555', 'Monthly Basic subscription', '2026-02-15'
FROM customers c JOIN subscriptions s ON s.subscription_id='SUB-001002' WHERE c.customer_id='CUST-001002'
ON CONFLICT (transaction_id) DO NOTHING;
