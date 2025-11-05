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
def get_database_connection():
    conn_info = st.secrets["connections"]["postgresql"]
    engine = create_engine(
        f"postgresql://{conn_info['username']}:{conn_info['password']}@{conn_info['host']}:{conn_info['port']}/{conn_info['database']}"
    )
    return engine

@st.cache_data
def load_main_data():
    engine = get_database_connection()
    return pd.read_sql("SELECT * FROM combined_datastore", engine)

@st.cache_data  
def load_firmographics():
    engine = get_database_connection()
    return pd.read_sql("SELECT * FROM demandbase_techno_f5", engine)

@st.cache_data
def load_contacts():
    engine = get_database_connection()
    return pd.read_sql("SELECT * FROM bqresultsno3", engine)

# =====================================================
# LOAD DATASETS
# =====================================================
df = load_main_data()
db_df = load_firmographics() 
contacts_df = load_contacts()

st.sidebar.success("✅ All datasets loaded from PostgreSQL!")

# =====================================================
# NORMALIZE COLUMN HEADERS AND ALIGN SCHEMAS
# =====================================================
df.columns = df.columns.str.strip()
db_df.columns = db_df.columns.str.strip().str.lower()
contacts_df.columns = contacts_df.columns.str.strip()

# ✅ Standardize known key columns
if "customerid_nar" in db_df.columns:
    db_df.rename(columns={"customerid_nar": "CustomerId_NAR"}, inplace=True)
if "account_name" in db_df.columns:
    db_df.rename(columns={"account_name": "Account Name"}, inplace=True)
if "sales_buying_role_code" in contacts_df.columns:
    contacts_df.rename(columns={"sales_buying_role_code": "Buying Role"}, inplace=True)

# =====================================================
# ACCOUNT DROPDOWN
# =====================================================
st.sidebar.header("Select an Account")

if "Account Name" in df.columns:
    account_options = sorted(df["Account Name"].dropna().unique())
    account_choice = st.sidebar.selectbox(
        "Account (search and select one)",
        options=[""] + account_options,
        index=0,
        placeholder="Search and select an account..."
    )
else:
    st.error("No 'Account Name' column found in dataset.")
    st.stop()

if not account_choice:
    st.info("Please select an account to view its data.")
    st.stop()

st.session_state["account_choice"] = account_choice

# [Keep all the rest of your code exactly the same from "FILTER DATA FOR SELECTED ACCOUNT" onwards...]
# =====================================================
# FILTER DATA FOR SELECTED ACCOUNT
# =====================================================
account_data = df[df["Account Name"] == account_choice].copy()
if account_data.empty:
    st.warning("No data available for this account.")
    st.stop()

# Normalize date columns
for col in ["Activity Date", "Activity_DateOnly", "Date"]:
    if col in account_data.columns:
        account_data["__date_col__"] = pd.to_datetime(account_data[col], errors="coerce", utc=True)
        break

# =====================================================
# ENGAGEMENT TIMELINE
# =====================================================
st.subheader(f"Engagement Timeline for {account_choice}")

possible_first_cols = ["First Name", "first name", "first_name", "fname", "firstname", "first"]
possible_last_cols = ["Last Name", "last name", "last_name", "lname", "lastname", "last"]

cols_lower = {c.lower(): c for c in account_data.columns}
first_col = next((cols_lower[c.lower()] for c in possible_first_cols if c.lower() in cols_lower), None)
last_col = next((cols_lower[c.lower()] for c in possible_last_cols if c.lower() in cols_lower), None)

if not first_col or not last_col:
    st.error(f"❌ Could not find name columns in dataset. Columns available: {list(account_data.columns)[:50]}")
    st.stop()

account_data.rename(columns={first_col: "First Name", last_col: "Last Name"}, inplace=True)
named = account_data[(account_data["First Name"].notna()) & (account_data["First Name"].str.strip() != "")]

if not named.empty:
    named["Name + Role"] = named.apply(
        lambda x: f"{x['First Name']} {x['Last Name']} - {x['Buying Role']}"
        if pd.notna(x["Buying Role"]) and str(x["Buying Role"]).strip() != ""
        else f"{x['First Name']} {x['Last Name']}", axis=1
    )

    fig = px.scatter(
        named,
        x="__date_col__",
        y="Name + Role",
        color="First Name",
        symbol="Type" if "Type" in named.columns else None,
        hover_data={
            "Type": True,
            "Details": True if "Details" in named.columns else False,
            "__date_col__": "|%Y-%m-%d"
        },
        title=f"Engagement Timeline for {account_choice}",
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

# =====================================================
# FIRMOGRAPHICS
# =====================================================
st.subheader("Firmographics")

# Both datasets have CustomerId_NAR - let's join on that
if "CustomerId_NAR" in df.columns and "CustomerId_NAR" in db_df.columns:
    # Get the CustomerId_NAR values from the selected account
    account_customer_ids = df.loc[df["Account Name"] == account_choice, "CustomerId_NAR"].dropna().unique()
    
    # Find matching firmographics data
    firmographics = db_df[db_df["CustomerId_NAR"].isin(account_customer_ids)]
    
    if not firmographics.empty:
        # Remove columns that are completely empty or contain only NaN/empty strings
        non_empty_cols = []
        for col in firmographics.columns:
            if firmographics[col].notna().any() and (firmographics[col] != "").any():
                non_empty_cols.append(col)
        
        # Filter to only non-empty columns
        firmographics_clean = firmographics[non_empty_cols]
        
        # Show with bigger row height and scrollable
        st.dataframe(
            firmographics_clean,
            use_container_width=True,
            height=200,  # Bigger single row height
            column_config={
                col: st.column_config.TextColumn(
                    width="medium",
                    help=f"Data for {col}"
                ) for col in firmographics_clean.columns
            }
        )
        
        st.caption(f"Showing {len(firmographics_clean)} firmographics records with {len(non_empty_cols)} non-empty columns")
    else:
        st.info("No firmographics data found for this account.")
else:
    st.warning("CustomerId_NAR column missing from one of the datasets.")

# =====================================================
# CONTACTS SECTION
# =====================================================
possible_keys = ["party_number", "Party_Number", "party_id", "Party_ID"]
contact_key = next((k for k in possible_keys if k in contacts_df.columns), None)

if contact_key is None:
    st.error(f"❌ Could not find any of these join keys in contacts dataset: {possible_keys}")
    st.stop()

def normalize_id(x):
    if pd.isna(x):
        return None
    return str(x).strip().upper().replace("H-CIT-", "").replace("H-", "").replace("CIT-", "")

contacts_df["party_number_clean"] = contacts_df[contact_key].apply(normalize_id)
df["CustomerId_NAR_clean"] = df["CustomerId_NAR"].apply(normalize_id)

matching_ids = df.loc[df["Account Name"] == account_choice, "CustomerId_NAR_clean"].dropna().unique()
account_contacts = contacts_df[contacts_df["party_number_clean"].isin(matching_ids)].copy()

# Derive engagement matches
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

account_contacts["is_engaged"] = account_contacts.apply(has_engaged_match, axis=1)

if "sales_affinity_code" not in account_contacts.columns:
    account_contacts["sales_affinity_code"] = ""

def get_status_color(row):
    if str(row["sales_affinity_code"]).strip():
        return "purple"
    if row["is_engaged"]:
        return "yellow"
    return "red"

account_contacts["status_color"] = account_contacts.apply(get_status_color, axis=1)

# =====================================================
# CONTACT FILTERS
# =====================================================
st.sidebar.markdown("---")
st.sidebar.subheader("Contact Filters")

color_filter = st.sidebar.multiselect(
    "Show colors:", ["red", "yellow", "purple"],
    default=["red", "yellow", "purple"],
)
search_query = st.sidebar.text_input("🔎 Search name").strip().lower()

filtered_contacts = account_contacts[account_contacts["status_color"].isin(color_filter)].copy()
if search_query and "party_unique_name" in filtered_contacts.columns:
    filtered_contacts = filtered_contacts[
        filtered_contacts["party_unique_name"].astype(str).str.lower().str.contains(search_query, na=False)
    ]
import streamlit.components.v1 as components

# =====================================================
# CONTACT TILES - SMALLER WITH TOP FILTER
# =====================================================
st.subheader(f"Contacts for {account_choice}")

if filtered_contacts.empty:
    st.info(f"No contacts found for {account_choice}.")
else:
    # Calculate summary stats first
    has_affinity = filtered_contacts['sales_affinity_code'].notna() & (filtered_contacts['sales_affinity_code'].str.strip() != "") & (filtered_contacts['sales_affinity_code'] != "nan")
    purple_count = len(filtered_contacts[has_affinity])
    red_count = len(filtered_contacts[~has_affinity])
    yellow_dot_count = len(filtered_contacts[filtered_contacts['is_engaged'] == True])
    total_count = len(filtered_contacts)
    
    # Top row: Filter on left, Summary metrics on right
    filter_col, metric_col1, metric_col2, metric_col3, metric_col4 = st.columns([2, 1, 1, 1, 1])
    
    with filter_col:
        # Quick filter buttons
        st.write("**Quick Filters:**")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            show_affinity = st.checkbox("With Affinity", value=True)
        with col_b:
            show_no_affinity = st.checkbox("No Affinity", value=True)
        with col_c:
            show_engaged = st.checkbox("Show Engaged Only", value=False)
    
    # Summary metrics
    metric_col1.metric("With Affinity", purple_count)
    metric_col2.metric("No Affinity", red_count)
    metric_col3.metric("Marketing Engaged", yellow_dot_count)
    metric_col4.metric("Total", total_count)
    
    st.markdown("---")
    
    # Apply quick filters
    display_contacts = filtered_contacts.copy()
    
    if not show_affinity:
        display_contacts = display_contacts[~has_affinity]
    if not show_no_affinity:
        display_contacts = display_contacts[has_affinity]
    if show_engaged:
        display_contacts = display_contacts[display_contacts['is_engaged'] == True]
    
    # Build the HTML for smaller tiles
    tiles_html = """
    <div style="display: flex; flex-wrap: wrap; gap: 6px; padding: 8px;">
    """
    
    for _, contact in display_contacts.iterrows():
        name = contact.get("party_unique_name", "Unknown")
        title = contact.get("job_title", "")
        affinity = contact.get("sales_affinity_code", "")
        is_engaged = contact.get("is_engaged", False)
        
        # Clean up display text
        display_title = title if pd.notna(title) and str(title).strip() != "nan" else "No Title"
        display_affinity = affinity if pd.notna(affinity) and str(affinity).strip() != "nan" else ""
        
        # Determine colors - deeper, more professional
        if display_affinity:
            bg_color = "#4c1d95"  # Deep purple
            border_color = "#5b21b6"  # Slightly lighter purple border
        else:
            bg_color = "#991b1b"  # Deep red
            border_color = "#b91c1c"  # Slightly lighter red border
        
        # Yellow dot for engaged - more muted
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
    
    # Render using components
    components.html(tiles_html, height=500, scrolling=True)





    
