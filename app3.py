import streamlit as st

st.set_page_config(
    page_title="Citrix Data Dashboard - Test",
    layout="wide"
)

st.title("🟢 App is Running!")
st.write("If you can see this, the basic app works.")
st.write("Now we'll add database connection...")

# Test secrets access
try:
    if "connections" in st.secrets:
        st.success("✅ Secrets are accessible")
        if "postgresql" in st.secrets["connections"]:
            st.success("✅ PostgreSQL secrets found")
            conn_info = st.secrets["connections"]["postgresql"]
            st.write(f"Host: {conn_info['host']}")
            st.write(f"Port: {conn_info['port']}")
        else:
            st.error("❌ PostgreSQL secrets not found")
    else:
        st.error("❌ No secrets found")
except Exception as e:
    st.error(f"❌ Error accessing secrets: {e}")




    
