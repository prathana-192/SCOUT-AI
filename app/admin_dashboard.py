import streamlit as st
import pandas as pd
import os
import sys
from supabase import create_client, Client

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config
import rag_pipeline as rag 

# --- INITIALIZE SUPABASE ---
# This replaces get_db_connection()
try:
    supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
except Exception as e:
    st.error(f"Supabase Connection Failed: {e}")
    supabase = None

def load_table_data(table_name):
    """
    Fetches all rows from a Supabase table.
    Replaces the old SQL query execution.
    """
    try:
        response = supabase.table(table_name).select("*").execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error loading {table_name}: {e}")
        return pd.DataFrame()

def update_booking_status(booking_id, new_status):
    """Updates booking status in Supabase"""
    try:
        supabase.table("bookings").update({"status": new_status}).eq("id", booking_id).execute()
        return True
    except Exception as e:
        st.error(f"Update Failed: {e}")
        return False

def show_admin_panel():
    st.title("Admin Dashboard")
    
    # --- 1. FETCH DATA (Replaces SQL Queries) ---
    # We fetch raw tables and join them in Python (easier than Supabase Joins)
    df_bookings = load_table_data("bookings")
    df_customers = load_table_data("customers")
    
    # Pre-process: Join Customer Info into Bookings
    if not df_bookings.empty and not df_customers.empty:
        # Merge bookings with customers on customer_id
        # Supabase returns columns as lowercase, ensure your DB columns match
        df_full = pd.merge(
            df_bookings, 
            df_customers[['id', 'name', 'email']], 
            left_on='customer_id', 
            right_on='id', 
            how='left',
            suffixes=('', '_cust')
        )
        # Rename for the UI
        df_full.rename(columns={
            'id': 'Booking_ID',
            'name': 'Customer',
            'email': 'Email',
            'location': 'Destination',
            'module_name': 'Module',
            'booking_date': 'Date',
            'guest_count': 'Guests',
            'total_cost': 'Cost',
            'status': 'Status',
            'created_at': 'Booked_On'
        }, inplace=True)
    else:
        df_full = pd.DataFrame()

    # --- 2. GLOBAL METRICS ---
    total_bookings = len(df_full)
    
    # Calculate Revenue (Sum Cost where Status is not Cancelled)
    total_revenue = 0
    if not df_full.empty and 'Cost' in df_full.columns:
        # Convert to numeric just in case
        df_full['Cost'] = pd.to_numeric(df_full['Cost'], errors='coerce').fillna(0)
        total_revenue = df_full[df_full['Status'] != 'Cancelled']['Cost'].sum()
        
    total_customers = len(df_customers)

    # Metric Row
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Bookings", total_bookings)
    m2.metric("Total Revenue", f"INR {total_revenue:,.0f}")
    m3.metric("Total Customers", total_customers)
    
    st.divider()

    # --- MAIN TABS ---
    tab1, tab2, tab3, tab4 = st.tabs(["Bookings Management", "Analytics", "Customer Data", "Knowledge Base"])

    # ==========================================
    # TAB 1: BOOKINGS (Filters + Table + Actions)
    # ==========================================
    with tab1:
        st.subheader("Manage Bookings")
        
        # 1. FILTER SECTION
        with st.expander("Filter Options", expanded=True):
            f1, f2, f3 = st.columns(3)
            with f1:
                status_filter = st.selectbox("Filter by Status", ["All", "Confirmed", "Completed", "Cancelled"])
            with f2:
                # Dynamic Location Filter
                if not df_full.empty and 'Destination' in df_full.columns:
                    locations = ["All"] + df_full['Destination'].unique().tolist()
                else:
                    locations = ["All"]
                location_filter = st.selectbox("Filter by Destination", locations)
            with f3:
                search_term = st.text_input("Search Name/ID", placeholder="Type name...")

        # 2. APPLY FILTERS (Pandas Logic instead of SQL WHERE)
        if not df_full.empty:
            df_view = df_full.copy()

            if status_filter != "All":
                df_view = df_view[df_view['Status'] == status_filter]
            
            if location_filter != "All":
                df_view = df_view[df_view['Destination'] == location_filter]
                
            if search_term:
                # Search in Name or ID
                s_term = search_term.lower()
                df_view = df_view[
                    df_view['Customer'].str.lower().str.contains(s_term, na=False) | 
                    df_view['Booking_ID'].astype(str).str.contains(s_term)
                ]

            # Sort by Date
            if 'Booked_On' in df_view.columns:
                df_view = df_view.sort_values(by='Booked_On', ascending=False)

            # 3. DISPLAY TABLE
            # Select specific columns to display cleanly
            cols_to_show = ['Booking_ID', 'Customer', 'Email', 'Destination', 'Module', 'Date', 'Guests', 'Cost', 'Status']
            # Only show columns that exist (safety check)
            cols_to_show = [c for c in cols_to_show if c in df_view.columns]
            
            st.dataframe(df_view[cols_to_show], use_container_width=True, hide_index=True)
            
            st.divider()
            
            # 4. ACTION SECTION
            st.subheader("Update Booking Status")
            ac1, ac2, ac3 = st.columns([1, 2, 1])
            
            with ac1:
                # Smart Dropdown
                available_ids = df_view['Booking_ID'].tolist()
                selected_id = st.selectbox("Select Booking ID", available_ids)
            
            with ac2:
                new_status_action = st.selectbox("Change Status To", ["Confirmed", "Completed", "Cancelled"])
            
            with ac3:
                st.write("") 
                st.write("") 
                if st.button("Update Status"):
                    if update_booking_status(selected_id, new_status_action):
                        st.success(f"Booking #{selected_id} updated to {new_status_action}!")
                        st.rerun()
            
            # Download
            csv = df_view.to_csv(index=False).encode('utf-8')
            st.download_button("Download filtered data as CSV", csv, "bookings.csv", "text/csv")
            
        else:
            st.info("No bookings match your filters.")

    # ==========================================
    # TAB 2: ANALYTICS (Charts)
    # ==========================================
    with tab2:
        st.subheader("Business Intelligence")
        
        if not df_full.empty:
            # Filter valid bookings
            valid_an = df_full[df_full['Status'] != 'Cancelled']
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                # 1. REVENUE BY DESTINATION
                if 'Destination' in valid_an.columns:
                    st.markdown("### Revenue by Destination")
                    rev_by_loc = valid_an.groupby("Destination")["Cost"].sum()
                    st.bar_chart(rev_by_loc, color="#4CAF50")

            with col_b:
                # 2. POPULAR MODULES
                if 'Module' in valid_an.columns:
                    st.markdown("### Most Popular Packages")
                    mod_counts = valid_an['Module'].value_counts()
                    st.bar_chart(mod_counts, color="#FF9800")
            
        else:
            st.warning("Not enough data to generate charts. Add some bookings!")

    # ==========================================
    # TAB 3: CUSTOMERS
    # ==========================================
    with tab3:
        st.subheader("Customer Database")
        if not df_customers.empty:
            st.dataframe(df_customers, use_container_width=True)
        else:
            st.info("No customers found.")

    # ==========================================
    # TAB 4: KNOWLEDGE BASE
    # ==========================================
    with tab4:
        st.subheader("RAG System Health")
        
        docs_dir = os.path.join(config.BASE_DIR, "docs")
        if os.path.exists(docs_dir):
            files = [f for f in os.listdir(docs_dir) if f.endswith('.pdf')]
            st.write(f"**Currently Indexed PDFs ({len(files)}):**")
            for f in files:
                st.code(f"{f}")
            
            st.divider()
            if st.button("Refresh Knowledge Base"):
                with st.spinner("Processing new PDFs..."):
                    rag.initialize_knowledge_base()
                    st.success("Knowledge base updated successfully!")
        else:
            st.error("Docs folder missing.")

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    show_admin_panel()