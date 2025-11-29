import streamlit as st
import sqlite3
import pandas as pd
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config
import rag_pipeline as rag 

def get_db_connection():
    return sqlite3.connect(config.DB_PATH)

def load_data(query, params=()):
    """Safe data loader with error handling"""
    if not os.path.exists(config.DB_PATH):
        return pd.DataFrame()
    
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()
    return df

def update_booking_status(booking_id, new_status):
    """Updates booking status in DB"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status = ? WHERE id = ?", (new_status, booking_id))
    conn.commit()
    conn.close()

def show_admin_panel():
    st.title("Admin Dashboard")
    
    # --- GLOBAL METRICS ---
    conn = get_db_connection()
    try:
        total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        revenue_query = conn.execute("SELECT SUM(total_cost) FROM bookings WHERE status!='Cancelled'").fetchone()[0]
        total_revenue = revenue_query if revenue_query else 0
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    except:
        total_bookings, total_revenue, total_customers = 0, 0, 0
    finally:
        conn.close()

    # Metric Row
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Bookings", total_bookings)
    m2.metric("Total Revenue", f"INR {total_revenue:,.0f}")
    m3.metric("Total Customers", total_customers)
    
    st.divider()

    # --- MAIN TABS (No Emojis) ---
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
                loc_df = load_data("SELECT DISTINCT location FROM bookings WHERE location IS NOT NULL")
                locations = ["All"] + loc_df['location'].tolist() if not loc_df.empty else ["All"]
                location_filter = st.selectbox("Filter by Destination", locations)
            with f3:
                search_term = st.text_input("Search Name/ID", placeholder="Type name...")

        # 2. QUERY BUILDING
        query = """
            SELECT 
                b.id as Booking_ID,
                c.name as Customer,
                c.email as Email,
                b.location as Destination,
                b.module_name as Module,
                b.booking_date as Date,
                b.guest_count as Guests,
                b.total_cost as Cost,
                b.status as Status,
                b.created_at as Booked_On
            FROM bookings b
            JOIN customers c ON b.customer_id = c.id
            WHERE 1=1
        """
        params = []

        if status_filter != "All":
            query += " AND b.status = ?"
            params.append(status_filter)
        
        if location_filter != "All":
            query += " AND b.location = ?"
            params.append(location_filter)
            
        if search_term:
            query += " AND (c.name LIKE ? OR b.id LIKE ?)"
            params.append(f"%{search_term}%")
            params.append(f"%{search_term}%")

        query += " ORDER BY b.created_at DESC"

        # 3. DISPLAY TABLE
        df_bookings = load_data(query, tuple(params))
        
        if not df_bookings.empty:
            st.dataframe(df_bookings, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # 4. ACTION SECTION
            st.subheader("Update Booking Status")
            ac1, ac2, ac3 = st.columns([1, 2, 1])
            
            with ac1:
                # Smart Dropdown: Only shows IDs currently filtered
                available_ids = df_bookings['Booking_ID'].tolist()
                selected_id = st.selectbox("Select Booking ID", available_ids)
            
            with ac2:
                new_status_action = st.selectbox("Change Status To", ["Confirmed", "Completed", "Cancelled"])
            
            with ac3:
                st.write("") # Spacer
                st.write("") 
                if st.button("Update Status"):
                    update_booking_status(selected_id, new_status_action)
                    st.success(f"Booking #{selected_id} updated to {new_status_action}!")
                    st.rerun()
            
            # Download
            csv = df_bookings.to_csv(index=False).encode('utf-8')
            st.download_button("Download filtered data as CSV", csv, "bookings.csv", "text/csv")
            
        else:
            st.info("No bookings match your filters.")

    # ==========================================
    # TAB 2: ANALYTICS (Charts)
    # ==========================================
    with tab2:
        st.subheader("Business Intelligence")
        
        # Load all valid data for analytics
        analytics_query = """
            SELECT location, module_name, total_cost, created_at, status 
            FROM bookings 
            WHERE status != 'Cancelled'
        """
        df_an = load_data(analytics_query)
        
        if not df_an.empty:
            col_a, col_b = st.columns(2)
            
            with col_a:
                # 1. REVENUE BY DESTINATION (Bar Chart)
                st.markdown("### Revenue by Destination")
                rev_by_loc = df_an.groupby("location")["total_cost"].sum()
                st.bar_chart(rev_by_loc, color="#4CAF50") # Green bars

            with col_b:
                # 2. POPULAR MODULES (Bar Chart)
                st.markdown("### Most Popular Packages")
                mod_counts = df_an['module_name'].value_counts()
                st.bar_chart(mod_counts, color="#FF9800") # Orange bars
            
        else:
            st.warning("Not enough data to generate charts. Add some bookings!")

    # ==========================================
    # TAB 3: CUSTOMERS
    # ==========================================
    with tab3:
        st.subheader("Customer Database")
        df_customers = load_data("SELECT * FROM customers")
        st.dataframe(df_customers, use_container_width=True)

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