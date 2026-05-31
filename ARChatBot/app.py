import streamlit as st
import clickhouse_connect
import google.generativeai as genai
import re
import os
import time
import pandas as pd
from dotenv import load_dotenv

# =====================================================================
# 1. INITIALIZATION & SECURE CONFIGURATION
# =====================================================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")

# Professional page configuration
st.set_page_config(
    page_title="AR Data Assistant", 
    page_icon="🤖", 
    layout="centered"
)

# Cache connections so the app doesn't reconnect on every text submission
@st.cache_resource
def init_connections():
    genai.configure(api_key=GEMINI_API_KEY)
    # Using your preferred model
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    db_client = clickhouse_connect.get_client(
        host='localhost', 
        username='chatbot', 
        password=CLICKHOUSE_PASSWORD, 
        database='my_database'
    )
    return model, db_client

model, db_client = init_connections()

# =====================================================================
# 2. THE LLM SCHEMA PROMPT & BUSINESS RULES
# =====================================================================
SCHEMA_PROMPT = """
You are an expert Data Analyst using ClickHouse SQL. Write a query to answer the user's question.
Return ONLY the raw SQL query. Do not include explanations or markdown backticks.
Always add LIMIT 100 if returning unaggregated rows.

Database: my_database

Table 1: invoice_doc_header
Columns:
- invoice_id (UInt64)
- invoice_number (String)
- customer_id (UInt32)
- status (Enum8: 'Open', 'Closed')
- create_date (Date)
- due_date (Date)
- invoice_amount (Decimal)
- current_due (Decimal)

Table 2: customer_master
Columns:
- customer_id (UInt32)
- parent_id (UInt32)
- customer_name (String)

Rules:
- To get customer names, JOIN invoice_doc_header with customer_master ON customer_id.
- Overdue means: status = 'Open' AND due_date < today()
- Always use single quotes for strings (e.g., 'Open').
"""

# =====================================================================
# 3. SIDEBAR & INTERFACE SETTINGS
# =====================================================================
st.title("🤖 AR Data Assistant")
st.markdown("Ask questions about your 50 million invoices in plain English.")

with st.sidebar:
    st.header("⚙️ Optimization Settings")
    ai_format = st.checkbox(
        "Use AI Formatting", 
        value=False,
        help="Turning this off displays raw query data tables directly and saves 50% of your daily Gemini limits."
    )
    st.markdown("---")
    st.markdown("💡 **Tip:** If you encounter 429 rate limits, turn off AI Formatting to preserve your remaining API requests.")

# =====================================================================
# 4. CHAT HISTORY STATE MANAGEMENT
# =====================================================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant", 
            "content": "Hello! I am connected to your ClickHouse database. What would you like to know?"
        }
    ]

# Render historic messages to UI
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# =====================================================================
# 5. MAIN CHAT APPLICATION LOGIC
# =====================================================================
if user_question := st.chat_input("E.g., Which 5 customers have the highest open balances?"):
    
    # 1. Display and record user query
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)
        
    # 2. Process AI generation with dynamic loading status
    with st.chat_message("assistant"):
        with st.spinner("Analyzing parameters and querying ClickHouse..."):
            sql_prompt = f"{SCHEMA_PROMPT}\n\nUser Question: {user_question}\nSQL Query:"
            final_answer = ""
            generated_sql = ""
            
            # Setup localized telemetry dictionary
            metrics = {
                "time_sql_gen": 0.0,
                "time_db_query": 0.0,
                "time_response_format": 0.0,
                "tokens_input": 0,
                "tokens_output": 0
            }
            
            # Self-Healing Evaluation Loop (Up to 2 consecutive executions)
            for attempt in range(2):
                try:
                    # STEP A: Text-to-SQL Translation
                    start_time = time.time()
                    response = model.generate_content(sql_prompt)
                    metrics["time_sql_gen"] += (time.time() - start_time)
                    
                    if response.usage_metadata:
                        metrics["tokens_input"] += response.usage_metadata.prompt_token_count
                        metrics["tokens_output"] += response.usage_metadata.candidates_token_count
                    
                    generated_sql = re.sub(r"```sql\n|```", "", response.text).strip()
                    
                    # STEP B: Database Engine Query Evaluation
                    start_time = time.time()
                    query_result = db_client.query(generated_sql)
                    raw_data = query_result.result_rows
                    columns = query_result.column_names
                    metrics["time_db_query"] += (time.time() - start_time)
                    
                    # STEP C: Natural Language Response Structuring
                    if ai_format and raw_data:
                        format_prompt = f"""
                        User asked: "{user_question}"
                        Columns returned: {columns}
                        Data returned: {raw_data[:15]} 
                        Write a concise, professional response providing this answer. Format currency properly.
                        """
                        start_time = time.time()
                        format_response = model.generate_content(format_prompt)
                        metrics["time_response_format"] += (time.time() - start_time)
                        
                        if format_response.usage_metadata:
                            metrics["tokens_input"] += format_response.usage_metadata.prompt_token_count
                            metrics["tokens_output"] += format_response.usage_metadata.candidates_token_count
                            
                        final_answer = format_response.text
                    else:
                        final_answer = "Here is the dataset corresponding to your request:"
                        
                    break # Break out of loop if successfully reached the end of execution
                    
                except clickhouse_connect.driver.exceptions.DatabaseError as e:
                    if attempt == 1:
                        final_answer = f"I'm sorry, I couldn't structure a valid query execution sequence. Database Error: {str(e)}"
                    else:
                        # Auto healing fallback injection
                        sql_prompt = f"{SCHEMA_PROMPT}\nUser asked: {user_question}\nYou wrote: {generated_sql}\nError: {str(e)}\nRewrite the SQL to fix this error."
                
                except Exception as e:
                    error_str = str(e)
                    # Safe Interception of Rate Limiting Quota blocks
                    if "429" in error_str or "quota" in error_str.lower():
                        final_answer = "⚠️ **Gemini 3.5-Flash Quota Limit Reached.** The daily request ceiling has been hit. Please toggle off 'AI Formatting' to try using direct data routing, or wait a brief period before retrying."
                    else:
                        final_answer = f"System Exception Met: {error_str}"
                    break
            
            # 3. Output formatted conversation message
            st.markdown(final_answer)
            
            # 4. Render clean data grid if AI formatting is bypassed
            if not ai_format and 'raw_data' in locals() and raw_data:
                df = pd.DataFrame(raw_data, columns=columns)
                st.dataframe(df, use_container_width=True)
            
            # 5. Display Performance Expandable Panel
            with st.expander("📊 View Query Execution Metrics & Token Stats"):
                total_time = metrics["time_sql_gen"] + metrics["time_db_query"] + metrics["time_response_format"]
                total_tokens = metrics['tokens_input'] + metrics['tokens_output']
                
                # Use st.caption for small, clean, unformatted text
                st.caption(
                    f"**Latency:** SQL ({metrics['time_sql_gen']:.2f}s) | "
                    f"DB ({metrics['time_db_query']:.2f}s) | "
                    f"Format ({metrics['time_response_format']:.2f}s) ➔ "
                    f"**Total: {total_time:.2f}s**"
                )
                st.caption(
                    f"**Tokens:** Input ({metrics['tokens_input']:,}) | "
                    f"Output ({metrics['tokens_output']:,}) ➔ "
                    f"**Total: {total_tokens:,}**"
                )
                

                if generated_sql:
                    st.divider()
                    st.code(generated_sql, language="sql")
            
            # Record assistant state history 
            st.session_state.messages.append({"role": "assistant", "content": final_answer})