# AR Data Assistant (Accounts Receivable Chatbot)

An intelligent, high-performance Accounts Receivable (AR) Data Assistant powered by **Google Gemini** and **ClickHouse**. This system translates natural language queries into optimized ClickHouse SQL, executes queries against a massive 50-million-row dataset, and dynamically synthesizes natural language responses—all with built-in query self-healing and detailed telemetry.

---

## Key Features

*   **Natural Language to ClickHouse SQL**: Translates human-style questions (e.g., *"Which 5 customers have the highest open balances?"*) directly into highly optimized ClickHouse queries.
*   **High-Scale Performance**: Engineered to seamlessly query over **50,000,000 invoice records** in fractions of a second using ClickHouse's columnar engine.
*   **Self-Healing Query Loop**: If ClickHouse returns an SQL execution error, the system automatically feeds the error back to Gemini to self-heal and regenerate a corrected query.
*   **Granular Telemetry & Metrics**: Real-time display of execution latency (SQL generation, DB query execution, and NL formatting) and token usage stats.
*   **AI Formatting Optimization**: Toggleable AI formatting option. Disabling AI formatting saves up to 50% of API limits and displays raw, tabular database results directly.
*   ** Demo **: Includes a demo video (`ChatbotDemo.mp4`) and visual samples of reports (`invoice-due-14-days.png`).

---

## 📁 Repository Structure

```filepath
ClickHouseDemo/
├── .env                  # Environment secrets (Gemini API key & ClickHouse credentials)
├── docker-compose.yml    # ClickHouse server Docker configuration
├── gen_script.sql        # High-performance SQL script to generate 50M rows of synthetic AR data
├── requirements.txt      # Python dependencies
├── app.py                # Main Streamlit web application
├── model-check.py        # Utility script to list models supported by your Gemini API Key
├── ChatbotDemo.mp4       # Video demonstration of the AI assistant in action
└── invoice-due-14-days.png # Sample image asset showing visual metrics
```

---

## 📊 Database Schema & Scale

The ClickHouse database (`my_database`) contains a highly optimized, partitioned, and sorted schema designed to query millions of rows in milliseconds:

### `customer_master`
Stores customer hierarchy information. Contains L1 (Parent), L2, and L3 (End-Customer) customer mappings.
```sql
CREATE TABLE customer_master (
    customer_id UInt32,
    parent_id UInt32,
    customer_name String
) ENGINE = MergeTree()
ORDER BY customer_id;
```
*   `customer_id` — Primary identifier.
*   `parent_id` — Maps L2 customers back to L1 parents (0 for top-tier L1).
*   `customer_name` — Name of the customer.

### `invoice_doc_header`
Stores invoice metadata. Partitioned monthly and sorted by customer, status, and due date to optimize query performance.
```sql
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
```
*   `invoice_id` — Unique invoice identifier.
*   `invoice_number` — Formatted invoice number (e.g. `INV-XXXXXX`).
*   `customer_id` — Foreign key mapped to `customer_master`.
*   `status` — Current document status (`Open` or `Closed`).
*   `create_date` — Date when the invoice was issued (used for monthly partitioning).
*   `due_date` — Scheduled payment deadline.
*   `invoice_amount` — Total invoiced amount.
*   `current_due` — Unpaid balance remaining (0 for Closed invoices).

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have the following installed:
*   [Docker & Docker Compose](https://www.docker.com/)
*   [Python 3.10+](https://www.python.org/)
*   Gemini API Key (available from [Google AI Studio](https://aistudio.google.com/))

### 2. Run the ClickHouse Container
Spin up the local ClickHouse server in the background using Docker Compose:
```bash
docker compose up -d
```
*Note: This starts a ClickHouse server exposed on port `8123` (HTTP) and `9000` (Native TCP).*

### 3. Initialize Database, Generate 50M Records & Setup Chatbot User
Connect to your ClickHouse container to create the target database, run the synthetic data generation script, and configure user permissions:

```bash
# 1. Create the 'my_database' database using default admin credentials
docker exec -i clickhouse-server clickhouse-client --user default_user --password Pas7w0rd! --query "CREATE DATABASE IF NOT EXISTS my_database"

# 2. Run the generation script inside 'my_database' to rebuild tables, insert 50M rows, and set up the chatbot user
docker exec -i clickhouse-server clickhouse-client --user default_user --password Pas7w0rd! --database my_database < gen_script.sql
```

> [!NOTE]
> The generation script drops old tables (if any), creates `customer_master` and `invoice_doc_header` with standard high-performance indices, generates 50 million realistic invoice headers across 225,000 L3 customers, creates the `chatbot` user identified by `BotSaf3ty!`, and grants it read-only (`SELECT`) access on `my_database.*`.

### 4. Configure Environment Variables
Create a `.env` file in the root directory and configure your credentials:
```env
GEMINI_API_KEY=your_gemini_api_key_here
CLICKHOUSE_PASSWORD=BotSaf3ty!
```

### 5. Setup Python Virtual Environment & Install Dependencies
Create a virtual environment, activate it, and install dependencies:

**On Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6. Run Model Availability Verification
Ensure your API key is correctly set up and check compatible Gemini model identifiers:
```bash
python model-check.py
```

### 7. Launch the Streamlit App
Run the interactive chatbot UI:
```bash
streamlit run app.py
```
A browser tab will automatically open, pointing to the local web interface (usually `http://localhost:8501`).

---

## 💡 Usage Tips & Best Practices

1.  **AI Formatting Toggle**: In the sidebar, toggle the **"Use AI Formatting"** checkbox. 
    *   **Enabled (Default)**: Summarizes data queries in a friendly narrative format.
    *   **Disabled**: Renders raw dataframes instantly. Ideal for large lists or when you are close to hitting API rate limits.
2.  **Rate Limiting**: If you encounter `429 Rate Limit` exceptions, toggle **AI Formatting off** in the sidebar. This reduces the number of tokens and requests per execution by 50% by avoiding the NL response synthesis phase.
3.  **Self-Healing**: If you notice a minor syntax error in a complex query, ask the model to clarify. The app's engine is designed to attempt auto-correction under the hood on standard SQL errors.
