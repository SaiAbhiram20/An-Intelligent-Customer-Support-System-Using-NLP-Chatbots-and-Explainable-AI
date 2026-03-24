"""
Database Service Layer
Connection pooling + all queries for customer, order, transaction, subscription lookups.
"""

import os
import logging
import functools
from typing import Dict, List, Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

# ─── Connection Pool ──────────────────────────────────────────

_pool = None

def init_db():
    """Initialize the connection pool from env vars."""
    global _pool
    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            dbname=os.getenv('DB_NAME', 'customer_support'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )
        logger.info("Database connection pool initialized")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        _pool = None
        return False


def close_db():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_cursor():
    """Get a database cursor with auto-commit and connection return."""
    if not _pool:
        raise ConnectionError("Database pool not initialized")
    conn = _pool.getconn()
    try:
        conn.autocommit = True
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cursor
        cursor.close()
    finally:
        _pool.putconn(conn)


def db_operation(func):
    """Decorator: returns None on DB error instead of crashing."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConnectionError:
            logger.warning("Database not connected")
            return None
        except Exception as e:
            logger.error(f"DB error in {func.__name__}: {e}")
            return None
    return wrapper


# ═══════════════════════════════════════════════════════════════
# CUSTOMER LOOKUPS
# ═══════════════════════════════════════════════════════════════

@db_operation
def get_customer_by_id(customer_id: str) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT customer_id, email, first_name, last_name, phone,
                   created_at
            FROM customers WHERE customer_id = %s
        """, (customer_id.upper(),))
        row = cur.fetchone()
        return dict(row) if row else None


@db_operation
def get_customer_by_email(email: str) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT customer_id, email, first_name, last_name, phone,
                   created_at
            FROM customers WHERE email = %s
        """, (email.lower(),))
        row = cur.fetchone()
        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════
# ORDER LOOKUPS
# ═══════════════════════════════════════════════════════════════

@db_operation
def get_order_by_id(order_id: str) -> Optional[Dict]:
    """Full order with customer info, items, and related transaction."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT o.order_id, o.status, o.subtotal, o.tax, o.shipping_cost, o.total,
                   o.shipping_address_line1, o.shipping_city, o.shipping_state, o.shipping_postal_code,
                   o.tracking_number, o.carrier, o.order_date, o.shipped_date,
                   o.estimated_delivery, o.actual_delivery, o.delivered_date, o.notes,
                   c.customer_id, c.first_name, c.last_name, c.email
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.order_id = %s
        """, (order_id.upper(),))
        order = cur.fetchone()
        if not order:
            return None
        order = dict(order)

        # Fetch items
        cur.execute("""
            SELECT product_name, product_sku, quantity, unit_price, total_price
            FROM order_items WHERE order_id = (SELECT id FROM orders WHERE order_id = %s)
        """, (order_id.upper(),))
        order['items'] = [dict(r) for r in cur.fetchall()]

        # Fetch latest transaction for this order
        cur.execute("""
            SELECT transaction_id, type, status, amount, payment_method,
                   refund_eligible, refund_deadline, created_at as transaction_date
            FROM transactions
            WHERE order_id = (SELECT id FROM orders WHERE order_id = %s)
            ORDER BY created_at DESC LIMIT 1
        """, (order_id.upper(),))
        txn = cur.fetchone()
        order['transaction'] = dict(txn) if txn else None

        return order


@db_operation
def get_orders_by_customer(customer_id: str, limit: int = 5) -> Optional[List[Dict]]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT o.order_id, o.status, o.total, o.order_date,
                   o.tracking_number, o.carrier, o.estimated_delivery, o.actual_delivery
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE c.customer_id = %s
            ORDER BY o.order_date DESC LIMIT %s
        """, (customer_id.upper(), limit))
        return [dict(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════
# TRANSACTION LOOKUPS
# ═══════════════════════════════════════════════════════════════

@db_operation
def get_transaction_by_id(txn_id: str) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT t.transaction_id, t.type, t.status, t.amount, t.payment_method,
                   t.refund_eligible, t.refund_deadline, t.description,
                   t.created_at as transaction_date,
                   c.customer_id, c.first_name, c.last_name, c.email
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            WHERE t.transaction_id = %s
        """, (txn_id.upper(),))
        row = cur.fetchone()
        return dict(row) if row else None


@db_operation
def get_transactions_by_customer(customer_id: str, limit: int = 10) -> Optional[List[Dict]]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT t.transaction_id, t.type, t.status, t.amount, t.payment_method,
                   t.refund_eligible, t.description,
                   t.created_at as transaction_date
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            WHERE c.customer_id = %s
            ORDER BY t.created_at DESC LIMIT %s
        """, (customer_id.upper(), limit))
        return [dict(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════
# SUBSCRIPTION LOOKUPS
# ═══════════════════════════════════════════════════════════════

@db_operation
def get_subscription_by_id(sub_id: str) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.subscription_id, s.plan_name, s.plan_price, s.billing_cycle,
                   s.status, s.start_date, s.current_period_start, s.current_period_end,
                   s.auto_renew, s.cancelled_at as cancellation_date,
                   s.cancel_reason as cancellation_reason,
                   c.customer_id, c.first_name, c.last_name, c.email
            FROM subscriptions s
            JOIN customers c ON s.customer_id = c.id
            WHERE s.subscription_id = %s
        """, (sub_id.upper(),))
        row = cur.fetchone()
        return dict(row) if row else None


@db_operation
def get_subscription_by_customer(customer_id: str) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.subscription_id, s.plan_name, s.plan_price, s.billing_cycle,
                   s.status, s.start_date, s.current_period_start, s.current_period_end,
                   s.auto_renew
            FROM subscriptions s
            JOIN customers c ON s.customer_id = c.id
            WHERE c.customer_id = %s
            ORDER BY s.created_at DESC LIMIT 1
        """, (customer_id.upper(),))
        row = cur.fetchone()
        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════
# REFUND ELIGIBILITY CHECK
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# ANALYTICS & FEEDBACK
# ═══════════════════════════════════════════════════════════════

@db_operation
def log_interaction(session_id: str, user_message: str, detected_intent: str,
                    confidence_score: float, response_source: str,
                    handoff_recommended: bool) -> Optional[str]:
    """Insert a chat interaction record and return its UUID."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO chat_interactions
                (session_id, user_message, detected_intent, confidence_score,
                 response_source, handoff_recommended)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (session_id, user_message, detected_intent, confidence_score,
              response_source, handoff_recommended))
        row = cur.fetchone()
        return str(row['id']) if row else None


@db_operation
def save_feedback(interaction_id: str, rating: int, comment: str = None) -> Optional[Dict]:
    """Save user feedback for a chat interaction. Flags for retraining if rating <= 2."""
    retrain = rating <= 2
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO feedback (interaction_id, rating, comment, retrain_flag)
            VALUES (%s, %s, %s, %s)
            RETURNING id, retrain_flag
        """, (interaction_id, rating, comment, retrain))
        row = cur.fetchone()
        return dict(row) if row else None


@db_operation
def get_analytics_data() -> Optional[Dict]:
    """Aggregate metrics for the analytics dashboard."""
    with get_cursor() as cur:
        # Total queries
        cur.execute("SELECT COUNT(*) AS total FROM chat_interactions")
        total = cur.fetchone()['total']

        # Handoff rate
        cur.execute("SELECT COUNT(*) AS cnt FROM chat_interactions WHERE handoff_recommended = TRUE")
        handoffs = cur.fetchone()['cnt']

        # Average confidence
        cur.execute("SELECT COALESCE(AVG(confidence_score), 0) AS avg_conf FROM chat_interactions")
        avg_conf = float(cur.fetchone()['avg_conf'])

        # Intent distribution (top 10)
        cur.execute("""
            SELECT detected_intent, COUNT(*) AS cnt
            FROM chat_interactions
            WHERE detected_intent IS NOT NULL
            GROUP BY detected_intent
            ORDER BY cnt DESC
            LIMIT 10
        """)
        intent_dist = [dict(r) for r in cur.fetchall()]

        # Average feedback rating
        cur.execute("SELECT COALESCE(AVG(rating), 0) AS avg_rating, COUNT(*) AS total_feedback FROM feedback")
        fb_row = cur.fetchone()

        # Recent feedback (last 20)
        cur.execute("""
            SELECT f.rating, f.comment, f.retrain_flag, f.created_at,
                   ci.user_message, ci.detected_intent, ci.confidence_score
            FROM feedback f
            JOIN chat_interactions ci ON f.interaction_id = ci.id
            ORDER BY f.created_at DESC
            LIMIT 20
        """)
        recent_feedback = [dict(r) for r in cur.fetchall()]

        # Queries per day (last 14 days)
        cur.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt
            FROM chat_interactions
            WHERE created_at >= CURRENT_DATE - INTERVAL '14 days'
            GROUP BY DATE(created_at)
            ORDER BY day
        """)
        daily_volume = [dict(r) for r in cur.fetchall()]

        return {
            "total_queries": total,
            "handoff_count": handoffs,
            "resolution_rate": round((1 - handoffs / max(total, 1)) * 100, 1),
            "avg_confidence": round(avg_conf, 1),
            "avg_feedback_rating": round(float(fb_row['avg_rating']), 2),
            "total_feedback": fb_row['total_feedback'],
            "intent_distribution": intent_dist,
            "recent_feedback": recent_feedback,
            "daily_volume": daily_volume,
        }


@db_operation
def get_retrain_candidates(limit: int = 20) -> Optional[List[Dict]]:
    """Fetch poorly rated interactions flagged for NLP retraining."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT ci.id AS interaction_id, ci.user_message, ci.detected_intent,
                   ci.confidence_score, ci.response_source, ci.created_at,
                   f.rating, f.comment
            FROM feedback f
            JOIN chat_interactions ci ON f.interaction_id = ci.id
            WHERE f.retrain_flag = TRUE
            ORDER BY f.created_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════
# REFUND ELIGIBILITY CHECK
# ═══════════════════════════════════════════════════════════════

@db_operation
def check_refund_eligibility(order_id: str) -> Optional[Dict]:
    """Check if an order qualifies for refund based on status, date, and policy."""
    order = get_order_by_id(order_id)
    if not order:
        return {"eligible": False, "reason": "Order not found", "order": None}

    if order['status'] not in ('delivered', 'completed', 'returned'):
        return {
            "eligible": False,
            "reason": f"Order status is '{order['status']}'. Refunds are only available for delivered orders.",
            "order": order
        }

    txn = order.get('transaction')
    if txn:
        if txn['status'] == 'refunded':
            return {"eligible": False, "reason": "This order has already been refunded.", "order": order}
        if not txn.get('refund_eligible'):
            return {
                "eligible": False,
                "reason": f"This order is outside the 30-day refund window (deadline was {txn.get('refund_deadline')}).",
                "order": order
            }

    return {
        "eligible": True,
        "reason": "Order is eligible for a full refund.",
        "order": order,
        "refund_amount": float(order['total']),
        "refund_deadline": str(txn['refund_deadline']) if txn else None
    }
