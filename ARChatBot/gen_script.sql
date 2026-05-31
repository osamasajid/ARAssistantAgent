-- 1. Wipe the slate clean (Optional: Drop old tables if rebuilding)
DROP TABLE IF EXISTS customer_master;
DROP TABLE IF EXISTS invoice_doc_header;

-- 2. Create the Customer Master Table
CREATE TABLE customer_master (
    customer_id UInt32,
    parent_id UInt32,
    customer_name String
) ENGINE = MergeTree()
ORDER BY customer_id;

-- 3. Create the Invoice Header Table
CREATE TABLE invoice_doc_header (
    invoice_id UInt64,
    invoice_number String,
    customer_id UInt32,
    status Enum8('Open' = 1, 'Closed' = 2),
    create_date Date,
    due_date Date,
    invoice_amount Decimal(18, 2),
    current_due Decimal(18, 2)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(create_date)
ORDER BY (customer_id, status, due_date)
SETTINGS index_granularity = 8192;


-- 4. Insert 5,000 L1 Customers (IDs 1 to 5,000)
INSERT INTO customer_master
SELECT 
    number + 1 AS customer_id, 
    0 AS parent_id, 
    concat('Customer_L1_', toString(number + 1)) AS customer_name
FROM numbers(5000);

-- 5. Insert 20,000 L2 Customers (IDs 5,001 to 25,000) randomly mapped to L1
INSERT INTO customer_master
SELECT 
    number + 5001 AS customer_id, 
    (rand() % 5000) + 1 AS parent_id, 
    concat('Customer_L2_', toString(number + 5001)) AS customer_name
FROM numbers(20000);


-- 6. Insert 50,000,000 Invoices
INSERT INTO invoice_doc_header
SELECT 
    invoice_id,
    invoice_number,
    customer_id,
    status,
    create_date,
    -- Due Date Logic: Closed invoices were due 30 days after creation. 
    -- Open invoices are due somewhere around today.
    if(status = 'Closed', 
       create_date + toIntervalDay(30), 
       today() + toIntervalDay(toUInt32(rand() % 60) - 15)
    ) AS due_date,
    invoice_amount,
    -- Current Due Logic: Closed invoices are 0. Open invoices have a random balance.
    if(status = 'Closed', 
       toDecimal64(0, 2), 
       toDecimal64(invoice_amount * ((rand() % 100) / 100), 2)
    ) AS current_due
FROM (
    -- Subquery generates base random data so `status` and `invoice_amount` 
    -- aren't re-evaluated by the IF statements in the outer query
    SELECT
        rand64() AS invoice_id,
        concat('INV-', toString(rand() % 99999999)) AS invoice_number,
        customer_distribution.customer_id AS customer_id,
        if(rand() % 100 < 90, 'Closed', 'Open') AS status, -- 90% Closed, 10% Open
        today() - toIntervalDay(toUInt32(rand() % 700)) AS create_date,
        toDecimal64((rand() % 1000000) / 100.0 + 100.0, 2) AS invoice_amount
    FROM (
        -- Step 1: Assign the exact invoice counts to the 225,000 L3 Customers
        SELECT 
            number + 25001 AS customer_id, -- L3 Customers start at ID 25001
            multiIf(
                number < 180000, toUInt32((rand() % 46) + 5),     -- 80% (180,000 users): 5 to 50 invoices
                number < 202500, toUInt32((rand() % 501) + 500),  -- 10% ( 22,500 users): 500 to 1000 invoices
                toUInt32((rand() % 4001) + 1000)                  -- 10% ( 22,500 users): 1000 to 5000 invoices
            ) AS assigned_count
        FROM numbers(225000)
    ) AS customer_distribution
    -- Step 2: Instantly fan out the customers into millions of rows based on their assigned count
    ARRAY JOIN range(assigned_count) AS _idx
)
-- Hard cap the output to ensure exactly 50,000,000 invoices are inserted
LIMIT 50000000;


--7 Creates Chatbot user and grant it permission to query the database
CREATE USER IF NOT EXISTS chatbot IDENTIFIED WITH plaintext_password BY 'BotSaf3ty!';
GRANT SELECT ON my_database.* TO chatbot;
