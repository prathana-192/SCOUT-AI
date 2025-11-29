import streamlit as st
import json
import re
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
import tools as tools
import models.llm as llm
import os

# --- LOAD DATA ---
def load_logistics():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, "app", "data", "logistics.json")
        with open(json_path, "r") as f:
            data = json.load(f)
        return data["destinations"]
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return {}

DESTINATIONS = load_logistics()

# --- STATE MANAGEMENT ---
def init_booking_state():
    if "booking_step" not in st.session_state:
        st.session_state.booking_step = "IDLE" 
    if "booking_data" not in st.session_state:
        st.session_state.booking_data = {
            "location": None, "module_key": None, "module_name": None,
            "date": None, "nights": 1, "guests": None,
            "total_cost": 0, "itinerary": "", "policy": "", "food": "",
            "name": None, "email": None, "phone": None
        }

def reset_booking_state():
    st.session_state.booking_step = "IDLE"
    st.session_state.booking_data = {k: None for k in st.session_state.booking_data}

# --- HISTORY SCANNER ---
def scan_history_for_intent(chat_history):
    if not chat_history: return {}
    found_data = {}
    for msg in reversed(chat_history):
        content = msg["content"].lower()
        for loc in DESTINATIONS.keys():
            if loc in content:
                found_data["location"] = loc
                break
        if not found_data.get("location"):
            for loc, details in DESTINATIONS.items():
                for mod_key, mod_val in details["modules"].items():
                    if mod_val["name"].lower() in content:
                        found_data["location"] = loc
                        found_data["service_type"] = mod_val["name"]
                        break
                if found_data.get("location"): break
        if found_data.get("location"): return found_data
    return {}

# --- EXTRACTOR ---
def extract_details(text, context_hint=""):
    groq = llm.get_chatgroq_model()
    valid_locs = list(DESTINATIONS.keys())
    prompt = f"""
    Extract booking entities from: "{text}". Context: {context_hint}.
    Today: {datetime.now().strftime("%Y-%m-%d")}.
    Valid Locations: {valid_locs}.
    Return JSON with keys: location, date (YYYY-MM-DD), guests (int), service_type, name, email, phone.
    """
    try:
        res = groq.invoke([SystemMessage(content=prompt)]).content
        return json.loads(res.replace("```json", "").replace("```", "").strip())
    except: return {}

# --- MATCHERS ---
def match_location(user_input_loc):
    if not user_input_loc: return None
    clean_input = user_input_loc.lower()
    for key in DESTINATIONS.keys():
        if key in clean_input or clean_input in key: return key
    return None

# --- IMPROVED MODULE MATCHER ---
def match_module(loc_key, user_text):
    """Finds best matching module from text."""
    if not user_text: return None
    user_text = user_text.lower()
    modules = DESTINATIONS[loc_key]["modules"]
    
    # 1. Check for "Package" or "3 Day" keywords specifically
    # This maps "Book this plan" -> "3-Day Full Adventure Pack"
    if any(w in user_text for w in ["3 day", "3-day", "package", "full trip", "plan", "all"]):
        if "module_combo" in modules:
            return "module_combo"

    # 2. Check for specific module names
    for m_key, m_val in modules.items():
        if m_val["name"].lower() in user_text or m_key in user_text:
            return m_key
            
    # 3. Check for generic types (Glamping, Trek)
    if "glamp" in user_text:
        for m_key, m_val in modules.items():
            if "glamp" in m_val["type"].lower(): return m_key
            
    return None

# --- MAIN FLOW ---
def process_booking_input(user_input, chat_history=[]):
    init_booking_state()
    step = st.session_state.booking_step
    data = st.session_state.booking_data
    
    # 1. START
    if step == "IDLE":
        user_lower = user_input.lower()
        if "update" in user_lower or "change" in user_lower:
            st.session_state.booking_data["intent"] = "update"
            st.session_state.booking_step = "WAITING_FOR_INVOICE"
            return "To update your booking, I first need to verify it. \n\nPlease upload your Booking PDF (Invoice) in the sidebar."

        if "cancel" in user_lower:
            st.session_state.booking_data["intent"] = "cancel"
            st.session_state.booking_step = "WAITING_FOR_INVOICE"
            return "To cancel, I need to verify your booking. \n\nPlease upload your Booking PDF in the sidebar."

        if any(w in user_input.lower() for w in ["book", "reserve"]):
            explicit = extract_details(user_input, "Booking Intent")
            if explicit.get("location"): st.session_state.booking_data.update(explicit)
            
            if not st.session_state.booking_data.get("location"):
                context = scan_history_for_intent(chat_history)
                if context.get("location"): st.session_state.booking_data.update(context)
            
            data = st.session_state.booking_data 

            found_key = match_location(data["location"])
            if found_key:
                st.session_state.booking_data["location"] = found_key
                data = st.session_state.booking_data # Refresh
                
                # 1. Try to find module from context (History) or input
                # Combine user input with any service_type found in history
                user_text_combined = user_input + " " + data.get("service_type", "")
                found_mod = match_module(found_key, user_text_combined)
                
                if found_mod:
                    st.session_state.booking_data["module_key"] = found_mod
                
                # 2. GENERATE TABLE (Now with Filter!)
                # If we found a specific module (like Module C), we pass it to the tool
                df = tools.get_availability_df(found_key, filter_module=found_mod)
                
                if df is not None and not df.empty:
                    st.session_state.selection_df = df
                    st.session_state.booking_step = "WAITING_FOR_SELECTION"
                    
                    # Custom message based on whether we filtered or not
                    if found_mod:
                        mod_name = DESTINATIONS[found_key]["modules"][found_mod]["name"]
                        return f"Here are the available slots for **{mod_name}** in {found_key.title()}: \n\n **Click a row to confirm:**"
                    else:
                        return f"I found several options for **{found_key.title()}**. \n\n **Please select a package from the table:**"
                
                # Fallback
                st.session_state.booking_step = "CHECK_DATE"
                return f"When do you want to visit {found_key.title()}?"

    if step == "WAITING_FOR_INVOICE":
        if "INVOICE_VERIFIED" in user_input:
            b_data = st.session_state.booking_data["verified_booking"]
            # RETRIEVE THE INTENT (Saved from Step 1)
            intent = st.session_state.booking_data.get("intent", "cancel")
            
            # Common Verification Message
            msg = (
                f"✅ **Verification Successful!**\n\n"
                f"Found Booking #{b_data['id']}\n"
                f"👤 Name: {b_data['name']}\n"
                f"📅 Date: {b_data['booking_date']}\n"
                f"⛺ Type: {b_data['service_type']}\n\n"
            )
            
            # --- BRANCH 1: UPDATE FLOW ---
            if intent == "update":
                st.session_state.booking_step = "ASK_UPDATE_DETAILS"
                return msg + "What would you like to change? (e.g., 'Change date to 2025-12-25' or 'Change guests to 4')"
            
            # --- BRANCH 2: CANCEL FLOW ---
            st.session_state.booking_step = "CONFIRM_CANCEL"
            return msg + "Based on our policy, you are eligible for cancellation.\n**Are you sure you want to cancel this trip? (Yes/No)**"
        
        return "Please upload the PDF in the sidebar to continue."
    
    # --- NEW STATE: CONFIRM CANCEL ---
    if step == "CONFIRM_CANCEL":
        if "yes" in user_input.lower():
            b_data = st.session_state.booking_data["verified_booking"]
            
            # 1. Send Email First (Strict Rule)
            sent = tools.send_cancellation_email(b_data["email"], b_data["name"], b_data["id"])
            
            if sent:
                # 2. Update Database Only if Email Sent
                deleted = tools.delete_booking(b_data["id"])
                reset_booking_state()
                return f" **Cancelled.** Booking #{b_data['id']} has been removed. A confirmation email has been sent."
            else:
                return " **Error.** Could not send cancellation email. Database NOT updated. Please try again."
        
        elif "no" in user_input.lower():
            reset_booking_state()
            return "Cancellation aborted. Your booking remains active."
            
        return "Type **YES** to confirm cancellation."
    
    # --- NEW STEP: HANDLE TABLE SELECTION ---
    if step == "WAITING_FOR_SELECTION":
        # Check if Main.py sent a "CONFIRMED_SELECTION" message
        if "CONFIRMED_SELECTION" in user_input:
            # Load Rich Data
            loc_key = data["location"]
            mod_key = data["module_key"]
            
            loc_data = DESTINATIONS[loc_key]
            mod_data = loc_data["modules"][mod_key]
            
            st.session_state.booking_data["module_name"] = mod_data["name"]
            st.session_state.booking_data["itinerary"] = mod_data.get("itinerary", "")
            st.session_state.booking_data["policy"] = loc_data.get("policy_summary", "")
            st.session_state.booking_data["food"] = loc_data.get("food_summary", "")
            
            st.session_state.booking_step = "VERIFY_SELECTION" # New Intermediate Step
            return f"You selected **{mod_data['name']}** on **{data['date']}**. \n\nIs this correct?"
        
        return "Please select a row from the table and click Confirm."

    # --- NEW STEP: RE-CONFIRMATION ---
    if step == "VERIFY_SELECTION":
        if "yes" in user_input.lower() or "correct" in user_input.lower():
            st.session_state.booking_step = "CHECK_GUESTS"
            return "Great! **How many guests** are joining?"
        else:
            # If user says no, reset to table
            st.session_state.booking_step = "IDLE"
            return "No problem. Let's start over. Where do you want to go?"

    # 3. GUESTS
    if step == "CHECK_GUESTS":
        guests = None
        
        # --- THE FIX STARTS HERE ---
        # 1. Try to find a number directly using Python (Fast & Reliable)
        digits = re.findall(r'\d+', user_input)
        if digits:
            guests = int(digits[0])
            
        # 2. If Python didn't find a number, ask the AI (Fallback)
        if not guests:
            ex = extract_details(user_input, "Guests")
            if ex.get("guests"):
                guests = int(ex["guests"])
        # --- THE FIX ENDS HERE ---

        # Logic Flow
        if guests:
            # Sanity check: Guests must be > 0
            if guests < 1: return "Please enter at least 1 guest."
            
            is_avail, msg = tools.check_availability(data["location"], data["module_key"], data["date"], guests)
            if is_avail:
                st.session_state.booking_data["guests"] = guests
                st.session_state.booking_step = "GET_DETAILS"
                return "Perfect! Slots reserved. Now, what is your **Full Name**?"
            else:
                return f"Error: {msg}"
        
        return "Please enter a number (e.g., 2)."
    
    # 4. DETAILS
    if step == "GET_DETAILS":
        # A. Validate & Collect Name
        if not data["name"]:
            # Simple check: Name should be at least 2 chars and not a number
            if len(user_input) < 2 or user_input.isdigit():
                return "Please enter a valid **Full Name**."
            st.session_state.booking_data["name"] = user_input.title()
            return "Thanks! What is your **Email ID**?"

        # B. Validate & Collect Email
        if not data["email"]:
            # Regex for Email Validation
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, user_input):
                return " That doesn't look like a valid email. Please try again (e.g., name@example.com)."
            st.session_state.booking_data["email"] = user_input.lower()
            return "And your **Phone Number**?"

        # C. Validate & Collect Phone
        if not data["phone"]:
            # Strip non-digits
            digits = re.sub(r"\D", "", user_input)
            if len(digits) != 10:
                return f" Invalid number. Please enter exactly **10 digits** (You entered {len(digits)})."
            st.session_state.booking_data["phone"] = digits
        
        # All details collected? Calculate & Confirm
        loc_data = DESTINATIONS[data["location"]]
        price = loc_data["modules"][data["module_key"]]["price"]
        total = price * data["guests"] * data["nights"]
        st.session_state.booking_data["total_cost"] = total
        
        st.session_state.booking_step = "CONFIRM"
        return (
            f"**Please Confirm Final Details:**\n"
            f"📍 {data['location'].title()} | 📅 {data['date']}\n"
            f"⛺ {data['module_name']}\n"
            f"👥 {data['guests']} Guests | 💰 **Total: ₹{total}**\n\n"
            f"👤 {data['name']} | 📞 {data['phone']}\n"
            f"📧 {data['email']}\n\n"
            f"Type **YES** to generate ticket."
        )

    # 5. CONFIRM (Fixed Order)
    if step == "CONFIRM":
        if "yes" in user_input.lower():
            # 1. SAVE TO DB FIRST (To get the ID)
            booking_id = tools.create_booking(
                data["name"], data["email"], data["phone"],
                data["location"], data["module_name"], 
                data["date"], data["nights"], # Pass 'nights' for end date calculation
                data["guests"], data["total_cost"]
            )
            
            if booking_id:
                # 2. SEND EMAIL (Now we have the real ID)
                sent = tools.send_rich_email(data["email"], data["name"], booking_id, data)
                
                if sent:
                    reset_booking_state()
                    return f"✅ **Success!** Booking ID: #{booking_id}. Check your email!"
                else:
                    # 3. ROLLBACK IF EMAIL FAILS
                    tools.delete_booking(booking_id)
                    return "❌ Failed. Email could not be sent. Booking cancelled."
            else:
                return "❌ Database Error. Please try again."
        
        reset_booking_state()
        return "Booking Cancelled."
    
    # 4. HANDLE UPDATE (Accumulate changes loop)
    if step == "ASK_UPDATE_DETAILS":
        # A. Check if user is DONE
        if any(w in user_input.lower() for w in ["no", "done", "update", "confirm", "proceed", "yes"]):
            st.session_state.booking_step = "CONFIRM_UPDATE"
            b_data = st.session_state.booking_data["verified_booking"]
            new_date = st.session_state.booking_data.get("new_date", b_data["booking_date"])
            new_guests = st.session_state.booking_data.get("new_guests", b_data["guest_count"])
            
            return (
                f"**🔒 Final Confirmation:**\n\n"
                f"Updating Booking **#{b_data['id']}**\n"
                f"📅 Date: {b_data['booking_date']} ➝ **{new_date}**\n"
                f"👥 Guests: {b_data['guest_count']} ➝ **{new_guests}**\n\n"
                f"Type **'CONFIRM'** to update."
            )

        # B. Smart Extraction
        ex = extract_details(user_input, "Update Request")
        updates_found = False
        
        if ex.get("date"): 
            st.session_state.booking_data["new_date"] = ex["date"]
            updates_found = True
        
        digits = re.findall(r'\d+', user_input)
        if digits and not ex.get("date"): 
            st.session_state.booking_data["new_guests"] = int(digits[0])
            updates_found = True
        elif ex.get("guests"): 
            st.session_state.booking_data["new_guests"] = int(ex["guests"])
            updates_found = True

        # --- THE FIX: SHOW TABLE IF USER ASKS ABOUT DATE WITHOUT PROVIDING ONE ---
        if not updates_found:
            user_lower = user_input.lower()
            if "date" in user_lower or "available" in user_lower or "reschedule" in user_lower:
                # 1. Get Location from verified booking string "coorg | Module A"
                b_data = st.session_state.booking_data["verified_booking"]
                loc_name = b_data['service_type'].split("|")[0].strip()
                
                # 2. Generate Table
                df = tools.get_availability_df(loc_name)
                if df is not None:
                    st.session_state.selection_df = df
                    st.session_state.booking_step = "WAITING_FOR_UPDATE_SELECTION" # New Step
                    return "Sure! Here are the available dates. \n\n **Please select a new date from the table:**"

        if updates_found:
            curr_date = st.session_state.booking_data.get("new_date", "Unchanged")
            curr_guests = st.session_state.booking_data.get("new_guests", "Unchanged")
            return f"Got it. New Draft: **{curr_date}** with **{curr_guests} guests**. \n\nAny other changes, or type 'Done'?"
        
        return "I didn't catch a change. Please say 'Change guests to 5' or ask 'Show available dates'."

    # --- NEW STEP: HANDLE UPDATE TABLE CLICK ---
    if step == "WAITING_FOR_UPDATE_SELECTION":
        if "UPDATE_SELECTED" in user_input:
            # Main.py updated the session variable 'new_date'
            new_date = st.session_state.booking_data["new_date"]
            return f"Selected new date: **{new_date}**. \n\nAny other changes? (Type 'Done' to finish)."
        return "Please click a row in the table to select your new date."

    # 5. EXECUTE UPDATE (DB + Email)
    if step == "CONFIRM_UPDATE":
        if "confirm" in user_input.lower() or "yes" in user_input.lower():
            b_data = st.session_state.booking_data["verified_booking"]
            
            # Get final values (fallback to old if not changed)
            final_date = st.session_state.booking_data.get("new_date", b_data["booking_date"])
            final_guests = st.session_state.booking_data.get("new_guests", b_data["guest_count"])
            
            # 1. Update Database
            success = tools.update_booking_details(b_data["id"], final_date, final_guests, 0)
            
            if success:
                # 2. Send Email
                tools.send_update_email(
                    b_data["email"], b_data["name"], b_data["id"],
                    old_details={"date": b_data["booking_date"], "guests": b_data["guest_count"]},
                    new_details={"date": final_date, "guests": final_guests}
                )
                reset_booking_state()
                return f"✅ **Update Complete!** Booking #{b_data['id']} is now set for {final_date} with {final_guests} guests. Email sent."
            else:
                return "❌ Database Error. Update failed."
            
        reset_booking_state()
        return "Update Cancelled. Keeping original details."