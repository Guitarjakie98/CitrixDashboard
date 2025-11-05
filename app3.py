import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import streamlit.components.v1 as components

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Citrix Data Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.title("Citrix Data Dashboard")

# =====================================================
# DATABASE CONNECTION
# =====================================================
@st.cache_data
def get_db_connection():
    conn_info = st.secrets["connections"]["postgresql"]
    return f"postgresql://{conn_info['username']}:{conn_info['password']}@{conn_info['host']}:{conn_info['port']}/{conn_info['database']}"

# =====================================================
# LOAD ACCOUNT LIST ONLY
# =====================================================
@st.cache_data
def load_account_list():
    """Load just the account names and basic stats for the dropdown"""
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        df = pd.read_sql("""
            SELECT "Account Name", 
                   COUNT(*) as activity_count,
                   COUNT(CASE WHEN "First Name" IS NOT NULL AND "First Name" != '' THEN 1 END) as named_activities
            FROM combined_datastore 
            WHERE "Account Name" IS NOT NULL
            GROUP BY "Account Name"
            ORDER BY activity_count DESC
        """, engine)
        engine.dispose()
        st.sidebar.success(f"✅ Found {len(df):,} accounts")
        return df
    except Exception as e:
        st.error(f"Error loading accounts: {e}")
        return pd.DataFrame()

# =====================================================
# LOAD DATA FOR SELECTED ACCOUNT
# =====================================================
@st.cache_data
def load_account_data(account_name):
    """Load all data for a specific account"""
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        
        # Load main data for this account
        main_df = pd.read_sql(f"""
            SELECT * FROM combined_datastore 
            WHERE "Account Name" = '{account_name.replace("'", "''")}'
        """, engine)
        
        engine.dispose()
        return main_df
    except Exception as e:
        st.error(f"Error loading account data: {e}")
        return pd.DataFrame()

@st.cache_data
def load_account_firmographics(customer_ids):
    """Load firmographics for specific customer IDs"""
    if not customer_ids:
        return pd.DataFrame()
    
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        
        # Convert list to SQL IN clause
        ids_str = "','".join([str(id).replace("'", "''") for id in customer_ids])
        
        df = pd.read_sql(f"""
            SELECT * FROM demandbase_techno_f5_analysis 
            WHERE "CustomerId_NAR" IN ('{ids_str}')
        """, engine)
        
        engine.dispose()
        return df
    except Exception as e:
        st.error(f"Error loading firmographics: {e}")
        return pd.DataFrame()

@st.cache_data
def load_account_contacts(customer_ids):
    """Load contacts for specific customer IDs"""
    if not customer_ids:
        return pd.DataFrame()
    
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        
        # Normalize IDs for matching
        normalized_ids = []
        for id in customer_ids:
            clean_id = str(id).strip().upper().replace("H-CIT-", "").replace("H-", "").replace("CIT-", "")
            normalized_ids.append(clean_id)
        
        ids_str = "','".join([id.replace("'", "''") for id in normalized_ids])
        
        df = pd.read_sql(f"""
            SELECT * FROM bqresultsnov3 
            WHERE UPPER(REPLACE(REPLACE(REPLACE("party_number", 'H-CIT-', ''), 'H-', ''), 'CIT-', '')) IN ('{ids_str}')
        """, engine)
        
        engine.dispose()
        return df
    except Exception as e:
        st.error(f"Error loading contacts: {e}")
        return pd.DataFrame()

# =====================================================
# TOP 10 ACCOUNTS (FROM SUMMARY)
# =====================================================
st.subheader("Top 10 Accounts by Named Engagements")

account_summary = load_account_list()

if not account_summary.empty:
    top_accounts = account_summary.nlargest(10, 'named_activities')
    
    fig1 = px.bar(
        top_accounts,
        x="Account Name",
        y="named_activities",
        text="named_activities",
        color="named_activities",
        color_continuous_scale="Tealgrn",
        title="Top 10 Accounts with the Most Named Activities"
    )

    fig1.update_traces(textposition="outside")
    fig1.update_layout(
        xaxis_title="Account Name",
        yaxis_title="Named Activity Count",
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-30,
        height=500
    )
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.error("Could not load account summary")

st.markdown("---")

# =====================================================
# ACCOUNT DROPDOWN
# =====================================================
st.sidebar.header("Select an Account")

if not account_summary.empty:
    # Create a nice display format for the dropdown
    account_summary['display_name'] = account_summary.apply(
        lambda x: f"{x['Account Name']} ({x['activity_count']:,} activities)", axis=1
    )
    
    account_choice = st.sidebar.selectbox(
        "Account (search and select one)",
        options=[""] + account_summary['display_name'].tolist(),
        index=0,
        placeholder="Search and select an account..."
    )
    
    # Extract the actual account name
    if account_choice:
        selected_account = account_choice.split(" (")[0]  # Remove the activity count part
    else:
        selected_account = ""
else:
    st.error("No accounts available.")
    st.stop()

if not selected_account:
    st.info("Please select an account to view its detailed data.")
    st.stop()

# =====================================================
# LOAD DATA FOR SELECTED ACCOUNT
# =====================================================
with st.spinner(f"Loading data for {selected_account}..."):
    account_data = load_account_data(selected_account)

if account_data.empty:
    st.warning(f"No data found for {selected_account}")
    st.stop()

# Normalize columns
account_data.columns = account_data.columns.str.strip()

# Handle date columns
for col in ["Activity Date", "Activity_DateOnly", "Date"]:
    if col in account_data.columns:
        account_data["__date_col__"] = pd.to_datetime(account_data[col], errors="coerce", utc=True)
        break

st.sidebar.success(f"✅ Loaded {len(account_data):,} records for {selected_account}")

# =====================================================
# ENGAGEMENT TIMELINE
# =====================================================
st.subheader(f"Engagement Timeline for {selected_account}")

# Find name columns
possible_first_cols = ["First Name", "first name", "first_name", "fname", "firstname", "first"]
possible_last_cols = ["Last Name", "last name", "last_name", "lname", "lastname", "last"]

cols_lower = {c.lower(): c for c in account_data.columns}
first_col = next((cols_lower[c.lower()] for c in possible_first_cols if c.lower() in cols_lower), None)
last_col = next((cols_lower[c.lower()] for c in possible_last_cols if c.lower() in cols_lower), None)

if first_col and last_col:
    account_data.rename(columns={first_col: "First Name", last_col: "Last Name"}, inplace=True)
    named = account_data[(account_data["First Name"].notna()) & (account_data["First Name"].str.strip() != "")]

    if not named.empty:
        # Add buying role if available
        if "sales_buying_role_code" in account_data.columns:
            account_data.rename(columns={"sales_buying_role_code": "Buying Role"}, inplace=True)
        
        named["Name + Role"] = named.apply(
            lambda x: f"{x['First Name']} {x['Last Name']} - {x.get('Buying Role', 'Unknown Role')}"
            if pd.notna(x.get("Buying Role")) and str(x.get("Buying Role", "")).strip() != ""
            else f"{x['First Name']} {x['Last Name']}", axis=1
        )

        fig = px.scatter(
            named,
            x="__date_col__",
            y="Name + Role",
            color="First Name",
            symbol="Type" if "Type" in named.columns else None,
            hover_data={
                "Type": True if "Type" in named.columns else False,
                "Details": True if "Details" in named.columns else False,
                "__date_col__": "|%Y-%m-%d"
            },
            title=f"Engagement Timeline for {selected_account}",
            height=600
        )

        fig.update_layout(
            yaxis_title="Name + Buying Role",
            xaxis_title="Engagement Date",
            plot_bgcolor="rgba(0,0,0,0)",
            legend_title="Person / Type",
            hovermode="closest"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No named engagements found for this account.")
else:
    st.info("Name columns not found in the data.")

# =====================================================
# FIRMOGRAPHICS
# =====================================================
st.subheader("Firmographics")

# Get customer IDs for this account
customer_ids = account_data["CustomerId_NAR"].dropna().unique().tolist()

if customer_ids:
    with st.spinner("Loading firmographics..."):
        firmographics = load_account_firmographics(customer_ids)
    
    if not firmographics.empty:
        # Clean up columns
        firmographics.columns = firmographics.columns.str.strip().str.lower()
        
        # Remove empty columns
        non_empty_cols = []
        for col in firmographics.columns:
            if firmographics[col].notna().any() and (firmographics[col] != "").any():
                non_empty_cols.append(col)
        
        firmographics_clean = firmographics[non_empty_cols]
        
        st.dataframe(
            firmographics_clean,
            use_container_width=True,
            height=200
        )
        
        st.caption(f"Showing {len(firmographics_clean)} firmographics records")
    else:
        st.info("No firmographics data found for this account.")
else:
    st.info("No Customer IDs found for firmographics lookup.")

# =====================================================
# CONTACTS
# =====================================================
st.subheader(f"Contacts for {selected_account}")

if customer_ids:
    with st.spinner("Loading contacts..."):
        contacts_df = load_account_contacts(customer_ids)
    
    if not contacts_df.empty:
        # Clean up columns
        contacts_df.columns = contacts_df.columns.str.strip()
        
        # Match engaged names
        engaged_names = set()
        if not named.empty:
            engaged_names = set(zip(
                named["First Name"].fillna("").str.strip().str.lower(),
                named["Last Name"].fillna("").str.strip().str.lower(),
            ))

        def has_engaged_match(row):
            parts = str(row.get("party_unique_name", "")).strip().split()
            if len(parts) >= 2:
                first, last = parts[0].lower(), parts[-1].lower()
                return (first, last) in engaged_names
            return False

        contacts_df["is_engaged"] = contacts_df.apply(has_engaged_match, axis=1)

        # Add status colors
        def get_status_color(row):
            affinity = str(row.get("sales_affinity_code", "")).strip()
            if affinity and affinity != "nan":
                return "purple"
            if row.get("is_engaged", False):
                return "yellow"
            return "red"

        contacts_df["status_color"] = contacts_df.apply(get_status_color, axis=1)
        
        # Contact filters
        st.sidebar.markdown("---")
        st.sidebar.subheader("Contact Filters")

        color_filter = st.sidebar.multiselect(
            "Show colors:", ["red", "yellow", "purple"],
            default=["red", "yellow", "purple"],
        )
        search_query = st.sidebar.text_input("🔎 Search name").strip().lower()

        filtered_contacts = contacts_df[contacts_df["status_color"].isin(color_filter)].copy()
        if search_query and "party_unique_name" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts[
                filtered_contacts["party_unique_name"].astype(str).str.lower().str.contains(search_query, na=False)
            ]

        if not filtered_contacts.empty:
            # Summary metrics
            has_affinity = filtered_contacts['sales_affinity_code'].notna() & (filtered_contacts['sales_affinity_code'].str.strip() != "") & (filtered_contacts['sales_affinity_code'] != "nan")
            purple_count = len(filtered_contacts[has_affinity])
            red_count = len(filtered_contacts[~has_affinity])
            yellow_dot_count = len(filtered_contacts[filtered_contacts['is_engaged'] == True])
            total_count = len(filtered_contacts)
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("With Affinity", purple_count)
            col2.metric("No Affinity", red_count)
            col3.metric("Marketing Engaged", yellow_dot_count)
            col4.metric("Total", total_count)
            
            # Contact tiles (keeping your existing tile code)
            tiles_html = """
            <div style="display: flex; flex-wrap: wrap; gap: 6px; padding: 8px;">
            """
            
            for _, contact in filtered_contacts.iterrows():
                name = contact.get("party_unique_name", "Unknown")
                title = contact.get("job_title", "")
                affinity = contact.get("sales_affinity_code", "")
                is_engaged = contact.get("is_engaged", False)
                
                display_title = title if pd.notna(title) and str(title).strip() != "nan" else "No Title"
                display_affinity = affinity if pd.notna(affinity) and str(affinity).strip() != "nan" else ""
                
                if display_affinity:
                    bg_color = "#4c1d95"
                    border_color = "#5b21b6"
                else:
                    bg_color = "#991b1b"
                    border_color = "#b91c1c"
                
                yellow_dot = """
                <div style="position: absolute; top: 6px; left: 6px; width: 10px; height: 10px; 
                           background: #d97706; border-radius: 50%; border: 1px solid white;"></div>
                """ if is_engaged else ""
                
                tiles_html += f"""
                <div style="
                    background: {bg_color}; 
                    color: white; 
                    padding: 12px; 
                    border-radius: 6px; 
                    border: 2px solid {border_color}; 
                    width: 150px; 
                    height: 90px; 
                    position: relative;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    text-align: center;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                ">
                    {yellow_dot}
                    <div style="font-weight: 600; font-size: 13px; margin-bottom: 4px; line-height: 1.1;">{name}</div>
                    <div style="font-size: 10px; margin-bottom: 3px; opacity: 0.9; line-height: 1.0;">
                        {display_affinity.replace('_', ' ').title() if display_affinity else 'No Affinity'}
                    </div>
                    <div style="font-size: 11px; opacity: 0.95; line-height: 1.0;">{display_title}</div>
                </div>
                """
            
            tiles_html += "</div>"
            components.html(tiles_html, height=500, scrolling=True)
        else:
            st.info("No contacts match your filters.")
    else:
        st.info("No contacts found for this account.")
else:
    st.info("No Customer IDs available for contact lookup.")


    
