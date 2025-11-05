import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.title("🔍 Database Connection Test")

try:
    conn_info = st.secrets["connections"]["postgresql"]
    connection_string = f"postgresql://{conn_info['username']}:{conn_info['password']}@{conn_info['host']}:{conn_info['port']}/{conn_info['database']}"
    
    st.write("Attempting database connection...")
    engine = create_engine(connection_string)
    
    # Test with a simple query first
    df = pd.read_sql("SELECT 1 as test", engine)
    st.success("✅ Database connection successful!")
    
    # Then test your actual tables
    df = pd.read_sql("SELECT COUNT(*) as count FROM combined_datastore", engine)
    st.write(f"Records in combined_datastore: {df['count'].iloc[0]}")
    
    engine.dispose()
    
except Exception as e:
    st.error(f"❌ Database error: {e}")
    st.write("This might be because:")
    st.write("- Ngrok tunnel is down")
    st.write("- Database is not accessible")
    st.write("- Table doesn't exist")


    
