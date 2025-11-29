import streamlit as st
import os
import sys
from PIL import Image, ImageDraw
import booking_flow as booking

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config
import rag_pipeline as rag
import admin_dashboard as admin

st.set_page_config(page_title="Scout AI", page_icon="assets/logo.png", layout="wide")

def crop_to_circle(image):
    mask = Image.new('L', image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + image.size, fill=255)
    output = Image.new('RGBA', image.size, (0, 0, 0, 0))
    output.paste(image, (0, 0), mask=mask)
    return output

def main():
    rag.initialize_knowledge_base()

    with st.sidebar:
        logo_path = "assets/logo.png"
        if os.path.exists(logo_path):
            st.image(crop_to_circle(Image.open(logo_path)), width=180)
        st.markdown("<p style='text-align: center; color: #555;'>Your Camping & Travel Companion</p>", unsafe_allow_html=True)
        st.divider()
        menu = st.radio("Menu", ["Chat", "Admin Dashboard"])
        st.divider()
        st.subheader("📂 Upload Documents")
        uploaded_file = st.file_uploader("Upload PDF (Invoice or Info)", type="pdf")
        
        if uploaded_file is not None:
            # ROUTER LOGIC: Invoice vs. Knowledge Base
            if st.session_state.get("booking_step") == "WAITING_FOR_INVOICE":
                
                with st.spinner("Verifying Invoice..."):
                    # Call the Verification Tool
                    is_valid, b_data, msg = booking.tools.verify_booking_from_pdf(uploaded_file)
                    
                    if is_valid:
                        st.success("Invoice Verified!")
                        # Store verified data in session
                        if "booking_data" not in st.session_state: booking.init_booking_state()
                        st.session_state.booking_data["verified_booking"] = b_data
                        
                        # Advance the Chat Flow
                        response = booking.process_booking_input("INVOICE_VERIFIED", st.session_state.messages)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        st.rerun()
                    else:
                        st.error(msg)
            
            else:
                # Standard RAG Upload
                with st.spinner("Processing Knowledge Base..."):
                    result = rag.add_user_pdf_to_db(uploaded_file)
                    st.success(result)

    if menu == "Admin Dashboard":
        admin.show_admin_panel()
    else:
        st.markdown("""<h1 style='color: #1B4D3E; font-size: 3rem;'>Hi, I'm Scout AI. 🏕️</h1>
            <p style='font-size: 1.3rem; color: #666;'>Where is adventure calling you next?</p>
            <hr style='margin:0 0 30px 0;'>""", unsafe_allow_html=True)

        if "messages" not in st.session_state:
            st.session_state.messages = [{"role": "assistant", "content": "Hello! Ask me about Coorg, Wayanad, or Kodaikanal."}]

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # --- INTERACTIVE TABLE LOGIC ---
        if "selection_df" in st.session_state and st.session_state.booking_step == "WAITING_FOR_SELECTION":
            df = st.session_state.selection_df
            st.write("### 🏕️ Available Packages")
            event = st.dataframe(
                df[["Package", "Date", "Price", "Status"]], 
                on_select="rerun", 
                selection_mode="single-row",
                use_container_width=True,
                hide_index=True
            )

            # SHOW CONFIRMATION BUTTON IF ROW SELECTED
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                selected_row = df.iloc[selected_index]
                
                st.info(f"You selected: **{selected_row['Package']}** on **{selected_row['Date']}**")
                
                if st.button("✅ Confirm Selection", type="primary"):
                    # 1. Update Data
                    st.session_state.booking_data["module_key"] = selected_row["module_key"]
                    st.session_state.booking_data["date"] = selected_row["raw_date"]
                    
                    # 2. Add Visual Message
                    user_msg = f"I select {selected_row['Package']} on {selected_row['Date']}"
                    st.session_state.messages.append({"role": "user", "content": user_msg})
                    
                    # 3. Advance Flow (Send Secret Code)
                    response = booking.process_booking_input("CONFIRMED_SELECTION", st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    # 4. Clean up
                    del st.session_state.selection_df
                    st.rerun()
                # CHECK 2: Update Booking Table (THE NEW PART)
                
        elif "selection_df" in st.session_state and st.session_state.booking_step == "WAITING_FOR_UPDATE_SELECTION":
            df = st.session_state.selection_df
            st.write("### 📅 Select New Date")
            event = st.dataframe(
                df[["Date", "Status"]], 
                on_select="rerun", 
                selection_mode="single-row", 
                use_container_width=True, 
                hide_index=True
            )

            # SHOW CONFIRMATION BUTTON FOR UPDATE
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                selected_row = df.iloc[selected_index]
                
                st.info(f"New Date Selected: **{selected_row['Date']}**")
                
                if st.button("✅ Confirm New Date", type="primary"):
                    # 1. Update the "new_date" field
                    st.session_state.booking_data["new_date"] = selected_row["raw_date"]
                    
                    # 2. Add Visual Message
                    user_msg = f"I select date: {selected_row['Date']}"
                    st.session_state.messages.append({"role": "user", "content": user_msg})
                    
                    # 3. Advance Flow
                    response = booking.process_booking_input("UPDATE_SELECTED", st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    # 4. Clean up
                    st.session_state.booking_step = "ASK_UPDATE_DETAILS" 
                    del st.session_state.selection_df
                    st.rerun()

        # Chat Input
        if prompt := st.chat_input("Type here..."):
            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    booking_response = booking.process_booking_input(prompt, st.session_state.messages)
                    final = booking_response if booking_response else rag.query_rag(prompt, st.session_state.messages)
                    st.markdown(final)
                    st.session_state.messages.append({"role": "assistant", "content": final})
            
            # Rerun if ANY table interaction is expected
            if st.session_state.booking_step in ["WAITING_FOR_SELECTION", "WAITING_FOR_UPDATE_SELECTION"]:
                st.rerun()

if __name__ == "__main__":
    main()