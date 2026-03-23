# ═══════════════════════════════════════════════════════════════
# Database Setup Script (Windows PowerShell)
# Sets up PostgreSQL database with schema and sample data
# ═══════════════════════════════════════════════════════════════

param(
    [string]$DB_HOST = "localhost",
    [string]$DB_PORT = "9403",
    [string]$DB_NAME = "customer_support",
    [string]$DB_USER = "postgres",
    [string]$DB_PASSWORD = "Itachiuchiha@20"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Customer Support DB Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Set password env var for psql
$env:PGPASSWORD = $DB_PASSWORD

# 1. Test connection
Write-Host "[1/4] Testing PostgreSQL connection..." -ForegroundColor Yellow
try {
    $test = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -tc "SELECT 1" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Connection failed" }
    Write-Host "  OK - Connected to PostgreSQL" -ForegroundColor Green
} catch {
    Write-Host "  FAILED - Cannot connect to PostgreSQL" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Make sure:" -ForegroundColor Yellow
    Write-Host "    1. PostgreSQL is installed (https://www.postgresql.org/download/windows/)" -ForegroundColor White
    Write-Host "    2. PostgreSQL bin is in your PATH (e.g. C:\Program Files\PostgreSQL\16\bin)" -ForegroundColor White
    Write-Host "    3. The PostgreSQL service is running" -ForegroundColor White
    Write-Host "    4. Password is correct (default: postgres)" -ForegroundColor White
    exit 1
}

# 2. Create database
Write-Host "[2/4] Creating database '$DB_NAME'..." -ForegroundColor Yellow
$dbExists = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" 2>&1
if ($dbExists -match "1") {
    Write-Host "  Database already exists (will add tables)" -ForegroundColor Yellow
} else {
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -c "CREATE DATABASE $DB_NAME;" 2>&1 | Out-Null
    Write-Host "  Created database '$DB_NAME'" -ForegroundColor Green
}

# 3. Run schema
Write-Host "[3/4] Creating tables..." -ForegroundColor Yellow
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$ScriptDir\schema.sql" 2>&1 | Out-Null
Write-Host "  Tables created" -ForegroundColor Green

# 4. Load sample data
Write-Host "[4/4] Loading sample data..." -ForegroundColor Yellow
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$ScriptDir\sample_data.sql" 2>&1 | Out-Null
Write-Host "  Sample data loaded" -ForegroundColor Green

# Verify
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Record Counts:" -ForegroundColor Yellow
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
SELECT 'Customers' as table_name, COUNT(*) FROM customers
UNION ALL SELECT 'Orders', COUNT(*) FROM orders
UNION ALL SELECT 'Order Items', COUNT(*) FROM order_items
UNION ALL SELECT 'Transactions', COUNT(*) FROM transactions
UNION ALL SELECT 'Subscriptions', COUNT(*) FROM subscriptions;
"

Write-Host ""
Write-Host "Sample IDs for Testing:" -ForegroundColor Yellow
Write-Host ""
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
SELECT customer_id, first_name || ' ' || last_name as name FROM customers ORDER BY customer_id;
"
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
SELECT order_id, status, '$' || total as total FROM orders ORDER BY order_id;
"
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
SELECT transaction_id, type, status, '$' || amount as amount FROM transactions ORDER BY transaction_id LIMIT 8;
"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Test Messages to Try:" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host '  "What is the status of order ORD-100001?"' -ForegroundColor White
Write-Host '  "I want a refund for ORD-100002"' -ForegroundColor White
Write-Host '  "Where is my order ORD-100003?"' -ForegroundColor White
Write-Host '  "Show me customer CUST-001004 details"' -ForegroundColor White
Write-Host '  "Check transaction TXN-200001"' -ForegroundColor White
Write-Host '  "What subscription does CUST-001001 have?"' -ForegroundColor White
Write-Host ""

# Create .env file if it doesn't exist
$envPath = Join-Path $ScriptDir ".env"
if (-not (Test-Path $envPath)) {
    @"
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
PORT=5000
"@ | Set-Content $envPath
    Write-Host "Created .env file at $envPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. cd .. (go to backend root)" -ForegroundColor White
Write-Host "  2. pip install -r requirements.txt" -ForegroundColor White
Write-Host "  3. python app.py" -ForegroundColor White
Write-Host ""
