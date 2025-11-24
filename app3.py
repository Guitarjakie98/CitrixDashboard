import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import streamlit.components.v1 as components
import io
from datetime import datetime, timedelta

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
# DATA LOADING FUNCTIONS
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
        return df
    except Exception as e:
        st.error(f"Error loading accounts: {e}")
        return pd.DataFrame()

@st.cache_data
def load_account_data(account_name):
    """Load all data for a specific account"""
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        
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
    if not customer_ids: return pd.DataFrame()
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
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
    if not customer_ids: return pd.DataFrame()
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
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

@st.cache_data
def load_bulk_account_data(account_names):
    """Load data for multiple accounts at once"""
    if not account_names:
        return pd.DataFrame()
    
    try:
        connection_string = get_db_connection()
        engine = create_engine(connection_string)
        names_str = "','".join([str(n).replace("'", "''") for n in account_names])
        
        main_df = pd.read_sql(f"""
            SELECT * FROM combined_datastore 
            WHERE "Account Name" IN ('{names_str}')
        """, engine)
        
        engine.dispose()
        return main_df
    except Exception as e:
        st.error(f"Error loading bulk data: {e}")
        return pd.DataFrame()

# =====================================================
# TAB STRUCTURE
# =====================================================
tab_dashboard, tab_export = st.tabs(["📊 Account Deep Dive", "📥 Data Export"])

# =====================================================
# TAB 1: EXISTING DASHBOARD
# =====================================================
with tab_dashboard:
    st.subheader("Top 10 Accounts by Named Engagements")
    account_summary = load_account_list()

    if not account_summary.empty:
        top_accounts = account_summary.nlargest(10, 'named_activities')
        fig1 = px.bar(
            top_accounts, x="Account Name", y="named_activities", text="named_activities",
            color="named_activities", color_continuous_scale="Tealgrn",
            title="Top 10 Accounts with the Most Named Activities"
        )
        fig1.update_traces(textposition="outside")
        fig1.update_layout(xaxis_title="Account Name", yaxis_title="Named Activity Count",
                           showlegend=False, plot_bgcolor="rgba(0,0,0,0)", height=500)
        st.plotly_chart(fig1, use_container_width=True)
    
    st.markdown("---")
    
    st.sidebar.header("Dashboard Controls")
    selected_account = ""
    if not account_summary.empty:
        account_summary['display_name'] = account_summary.apply(
            lambda x: f"{x['Account Name']} ({x['activity_count']:,} activities)", axis=1
        )
        account_choice = st.sidebar.selectbox(
            "Select Account for Deep Dive",
            options=[""] + account_summary['display_name'].tolist(),
            index=0
        )
        if account_choice:
            selected_account = account_choice.split(" (")[0]

    if selected_account:
        with st.spinner(f"Loading data for {selected_account}..."):
            account_data = load_account_data(selected_account)

        if not account_data.empty:
            account_data.columns = account_data.columns.str.strip()
            for col in ["Activity Date", "Activity_DateOnly", "Date"]:
                if col in account_data.columns:
                    account_data["__date_col__"] = pd.to_datetime(account_data[col], errors="coerce", utc=True)
                    break

            # Timeline
            st.subheader(f"Engagement Timeline: {selected_account}")
            possible_first = ["First Name", "first name", "firstname", "first"]
            possible_last = ["Last Name", "last name", "lastname", "last"]
            cols_lower = {c.lower(): c for c in account_data.columns}
            f_col = next((cols_lower[c] for c in possible_first if c in cols_lower), None)
            l_col = next((cols_lower[c] for c in possible_last if c in cols_lower), None)

            named = pd.DataFrame()
            engaged_names = set()
            
            if f_col and l_col:
                account_data.rename(columns={f_col: "First Name", l_col: "Last Name"}, inplace=True)
                named = account_data[account_data["First Name"].notna() & (account_data["First Name"] != "")]
                if not named.empty:
                    engaged_names = set(zip(named["First Name"].fillna("").str.strip().str.lower(),
                                          named["Last Name"].fillna("").str.strip().str.lower()))
                    if "sales_buying_role_code" in account_data.columns:
                        account_data.rename(columns={"sales_buying_role_code": "Buying Role"}, inplace=True)
                    named["Label"] = named["First Name"] + " " + named["Last Name"]
                    
                    fig = px.scatter(named, x="__date_col__", y="Label", color="First Name", title="Timeline")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No named engagements.")

            # Firmographics
            st.subheader("Firmographics")
            cust_ids = account_data["CustomerId_NAR"].dropna().unique().tolist()
            if cust_ids:
                firmographics = load_account_firmographics(cust_ids)
                if not firmographics.empty:
                    st.dataframe(firmographics, use_container_width=True, height=200)
                else:
                    st.info("No firmographics data found.")
            else:
                st.info("No Customer IDs found.")

            # Contacts
            st.subheader("Contacts")
            if cust_ids:
                contacts = load_account_contacts(cust_ids)
                if not contacts.empty:
                    contacts.columns = contacts.columns.str.strip()
                    contacts["is_engaged"] = contacts.apply(lambda r: 
                        (str(r.get("party_unique_name","")).split()[0].lower(), 
                         str(r.get("party_unique_name","")).split()[-1].lower()) in engaged_names 
                        if len(str(r.get("party_unique_name","")).split())>=2 else False, axis=1)
                    
                    contacts["status_color"] = contacts.apply(lambda r: 
                        "purple" if pd.notna(r.get("sales_affinity_code")) and str(r.get("sales_affinity_code")).strip() != "nan" 
                        else ("yellow" if r["is_engaged"] else "red"), axis=1)

                    st.sidebar.markdown("---")
                    st.sidebar.subheader("Contact Filters")
                    color_filter = st.sidebar.multiselect("Show colors:", ["red", "yellow", "purple"], default=["red", "yellow", "purple"], key="contact_colors_tab1")
                    search_query = st.sidebar.text_input("🔎 Search name", key="contact_search_tab1").strip().lower()

                    filtered_contacts = contacts[contacts["status_color"].isin(color_filter)].copy()
                    if search_query and "party_unique_name" in filtered_contacts.columns:
                        filtered_contacts = filtered_contacts[filtered_contacts["party_unique_name"].astype(str).str.lower().str.contains(search_query, na=False)]

                    if not filtered_contacts.empty:
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("With Affinity", len(filtered_contacts[filtered_contacts['status_color'] == 'purple']))
                        c2.metric("No Affinity", len(filtered_contacts[filtered_contacts['status_color'] == 'red']))
                        c3.metric("Marketing Engaged", len(filtered_contacts[filtered_contacts['is_engaged'] == True]))
                        c4.metric("Total", len(filtered_contacts))
                        
                        tiles_html = """
                        <div style="display: flex; flex-wrap: wrap; gap: 6px; padding: 8px;">
                        """
                        
                        for _, contact in filtered_contacts.head(100).iterrows():
                            name = contact.get("party_unique_name", "Unknown")
                            title = contact.get("job_title", "")
                            affinity = contact.get("sales_affinity_code", "")
                            is_engaged = contact.get("is_engaged", False)
                            
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
                                <div style="font-size: 11px; opacity: 0.95; line-height: 1.0;">{title}</div>
                            </div>
                            """
                        
                        tiles_html += "</div>"
                        components.html(tiles_html, height=500, scrolling=True)
                    else:
                        st.info("No contacts match filters.")

# =====================================================
# TAB 2: DATA EXPORT
# =====================================================
with tab_export:
    st.header("Bulk Data Export")
    
    col_input, col_filters = st.columns(2)
    
    with col_input:
        st.subheader("1. Select Accounts")
        available_accounts = account_summary['Account Name'].tolist() if not account_summary.empty else []
        selected_from_dropdown = st.multiselect("Search & Select Accounts", available_accounts)
        pasted_text = st.text_area("Or Paste Account Names (one per line)", height=150, placeholder="Account A\nAccount B")
        
    with col_filters:
        st.subheader("2. Filter Activity Data")
        today = datetime.now()
        last_year = today - timedelta(days=365)
        date_range = st.date_input("Activity Date Range", [last_year, today])

    pasted_list = [x.strip() for x in pasted_text.split('\n') if x.strip()]
    final_selection = list(set(selected_from_dropdown + pasted_list))
    
    if final_selection:
        st.success(f"Selected {len(final_selection)} accounts for export.")
        
        with st.spinner("Fetching bulk data..."):
            bulk_activity_df = load_bulk_account_data(final_selection)
            
        if not bulk_activity_df.empty:
            # Safer Date Logic (with UTC)
            bulk_activity_df.columns = bulk_activity_df.columns.str.strip()
            date_col_found = None
            for col in ["Activity Date", "Activity_DateOnly", "Date"]:
                if col in bulk_activity_df.columns:
                    date_col_found = col
                    # Convert to datetime UTC
                    bulk_activity_df[col] = pd.to_datetime(bulk_activity_df[col], errors='coerce', utc=True)
                    break
            
            filtered_activity = bulk_activity_df.copy()
            
            # Filter Logic
            if date_col_found and len(date_range) == 2:
                dates_only = filtered_activity[date_col_found].dt.date
                start_d = date_range[0]
                end_d = date_range[1]
                
                filtered_activity = filtered_activity[
                    (dates_only >= start_d) & (dates_only <= end_d)
                ]

            all_cust_ids = bulk_activity_df["CustomerId_NAR"].dropna().unique().tolist()
            bulk_contacts_df = load_account_contacts(all_cust_ids)

            st.markdown("### Data Preview")
            t1, t2 = st.tabs(["Account Activity (Filtered)", "All Contacts (Unfiltered)"])
            
            with t1:
                st.dataframe(filtered_activity, use_container_width=True)
                st.caption(f"{len(filtered_activity)} rows | Date Filter: {date_range}")
                
            with t2:
                st.dataframe(bulk_contacts_df, use_container_width=True)
                st.caption(f"{len(bulk_contacts_df)} contacts found for selected accounts")

            st.markdown("### Export")
            
            # --- ULTIMATE TIMEZONE FIX ---
            # Iterate through ALL columns in both tables. 
            # If any column is a datetime with timezone info (UTC), strip it.
            # This guarantees Excel compliance for every single column.
            
            # 1. Clean Activity Data
            for col in filtered_activity.columns:
                if pd.api.types.is_datetime64_any_dtype(filtered_activity[col]):
                    if filtered_activity[col].dt.tz is not None:
                        filtered_activity[col] = filtered_activity[col].dt.tz_localize(None)

            # 2. Clean Contact Data
            for col in bulk_contacts_df.columns:
                if pd.api.types.is_datetime64_any_dtype(bulk_contacts_df[col]):
                     if bulk_contacts_df[col].dt.tz is not None:
                        bulk_contacts_df[col] = bulk_contacts_df[col].dt.tz_localize(None)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer) as writer:
                filtered_activity.to_excel(writer, sheet_name='Account Activity', index=False)
                bulk_contacts_df.to_excel(writer, sheet_name='Contacts', index=False)
                
            st.download_button(
                label="📥 Download Excel Report (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"citrix_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel"
            )

        else:
            st.warning("No data found for the selected accounts.")
    else:
        st.info("Please select or paste accounts to begin.")
