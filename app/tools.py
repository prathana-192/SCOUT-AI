import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys
import json
from datetime import datetime, timedelta
import pandas as pd
from langchain_community.document_loaders import PyPDFLoader
import re

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config

# --- HELPER: CALCULATE END DATE ---
def calculate_end_date(start_date_str, nights):
    """Calculates end date based on nights stay"""
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d")
        end = start + timedelta(days=int(nights))
        return end.strftime("%Y-%m-%d")
    except: return start_date_str

# --- DB TOOLS ---
def create_booking(name, email, phone, location, module, start_date, nights, guests, total_cost):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        # 1. Prepare Data
        end_date = calculate_end_date(start_date, nights)
        date_range_str = f"{start_date} to {end_date}"
        
        # Construct the 'service_type' string required by your DB schema
        # This combines location and module (e.g. "Coorg | Module A")
        service_details = f"{location} | {module}"
        
        # 2. Handle Customer
        cursor.execute("SELECT id FROM customers WHERE email = ?", (email,))
        cust = cursor.fetchone()
        if cust:
            customer_id = cust[0]
        else:
            cursor.execute("INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)", (name, email, phone))
            customer_id = cursor.lastrowid
            
        # 3. Insert Booking (NOW INCLUDING service_type)
        cursor.execute("""
            INSERT INTO bookings 
            (customer_id, service_type, location, module_name, booking_date, start_date, end_date, guest_count, total_cost, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Confirmed')
        """, (customer_id, service_details, location, module, date_range_str, start_date, end_date, guests, total_cost))
        
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return booking_id
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def delete_booking(booking_id):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        conn.commit()
        conn.close()
        return True
    except: return False

def get_bookings_by_email(email):
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM customers WHERE email = ?", (email,))
        cust = cursor.fetchone()
        if not cust: return []
        cursor.execute("SELECT id, service_type, booking_date, status FROM bookings WHERE customer_id = ?", (cust['id'],))
        return [dict(row) for row in cursor.fetchall()]
    except: return []

# --- AVAILABILITY TOOL (Mock Logic) ---
def check_availability(location, module_key, date, guests_requested):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, "app", "data", "logistics.json"), "r") as f:
            data = json.load(f)
        
        max_cap = data["destinations"][location]["modules"][module_key]["capacity"]
        
        if date.endswith("05") or date.endswith("25"):
            return False, f"Sorry, {date} is sold out! (Max capacity: {max_cap})"
        
        if guests_requested > max_cap:
            return False, f"We only have {max_cap} slots left. You asked for {guests_requested}."
            
        return True, f"Available! ({max_cap} slots open)"
    except:
        return True, "Available" 

# --- RICH EMAIL TOOL ---
def send_rich_email(to_email, name, booking_id, details):
    if "your_email" in config.SENDER_EMAIL:
        print(f" [SIMULATION] Rich Email sent to {to_email}")
        return True

    try:
        # Calculate End Date for display
        end_date = calculate_end_date(details['date'], details['nights'])
        
        msg = MIMEMultipart("alternative")
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Booking Confirmed! (ID: #{booking_id}) - Scout AI"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="padding: 20px; background-color: #f9f9f9;">
                <h2 style="color: #1B4D3E;">Camping Trip Confirmed! 🏕️</h2>
                <p>Hi <strong>{name}</strong>, your trip to <strong>{details['location'].title()}</strong> is booked.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr><td><strong>Booking ID</strong></td><td>#{booking_id}</td></tr>
                    <tr><td><strong>Module</strong></td><td>{details['module_name']}</td></tr>
                    <tr><td><strong>Dates</strong></td><td>{details['date']} to {end_date} ({details['nights']} Nights)</td></tr>
                    <tr><td><strong>Guests</strong></td><td>{details['guests']}</td></tr>
                    <tr><td><strong>Total Paid</strong></td><td><strong>₹{details['total_cost']}</strong></td></tr>
                </table>
                <p><strong>Itinerary:</strong> {details['itinerary']}</p>
                <p><strong>Food:</strong> {details['food']}</p>
                <p style="color: #666; font-size: 12px;">Policy: {details['policy']}</p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        server.sendmail(config.SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- NEW TOOL: GET UPCOMING DATES ---
def get_availability_preview():
    today = datetime.now()
    available_dates = []
    for i in range(30):
        future_date = today + timedelta(days=i)
        if future_date.weekday() in [4, 5]: # Fri, Sat
            d_str = future_date.strftime("%Y-%m-%d")
            if not (d_str.endswith("05") or d_str.endswith("25")):
                available_dates.append(future_date.strftime("%d-%b (%a)"))
                if len(available_dates) >= 4: break
    return ", ".join(available_dates)

# --- NEW TOOL: GENERATE AVAILABILITY TABLE ---
def get_availability_df(location, filter_module=None):
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, "app", "data", "logistics.json"), "r") as f:
            data = json.load(f)
        
        loc_data = data["destinations"].get(location.lower())
        if not loc_data: return None

        table_rows = []
        today = datetime.now()
        
        valid_dates = []
        for i in range(30):
            future_date = today + timedelta(days=i)
            if future_date.weekday() in [4, 5]:
                d_str = future_date.strftime("%Y-%m-%d")
                d_pretty = future_date.strftime("%d-%b (%a)")
                if not (d_str.endswith("05") or d_str.endswith("25")):
                    valid_dates.append((d_str, d_pretty))
                if len(valid_dates) >= 3: break

        modules_to_show = loc_data["modules"]
        if filter_module and filter_module in modules_to_show:
            modules_to_show = {filter_module: modules_to_show[filter_module]}

        for mod_key, mod_val in modules_to_show.items():
            for d_raw, d_pretty in valid_dates:
                slots = mod_val["capacity"]
                if d_raw.endswith("1"): slots = 2
                status = f" {slots} Slots" if slots > 5 else f" Only {slots} left"
                
                table_rows.append({
                    "Package": mod_val["name"],
                    "Date": d_pretty,
                    "Price": f"₹{mod_val['price']}",
                    "Status": status,
                    "raw_date": d_raw,
                    "module_key": mod_key
                })

        return pd.DataFrame(table_rows)
    except Exception as e:
        print(f"Table Error: {e}")
        return None
    
def verify_booking_from_pdf(uploaded_file):
    """
    Reads a PDF, finds 'Booking ID: #123', and checks DB.
    Returns: (IsValid, BookingDetails_Dict, Message)
    """
    try:
        # 1. Save Temp File
        temp_path = f"temp_invoice_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # 2. Extract Text
        loader = PyPDFLoader(temp_path)
        pages = loader.load()
        full_text = "\n".join([p.page_content for p in pages])
        os.remove(temp_path) # Clean up
        
        # 3. Find Booking ID using Regex
        match = re.search(r"Booking ID\D+#(\d+)", full_text, re.IGNORECASE)
        
        if not match:
            return False, None, "Could not find a valid 'Booking ID: #...' in this document."
            
        booking_id = int(match.group(1))
        
        # 4. Verify in Database
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # FIXED QUERY: Added 'b.guest_count'
        cursor.execute("""
            SELECT b.id, b.service_type, b.booking_date, b.guest_count, b.status, c.email, c.name 
            FROM bookings b
            JOIN customers c ON b.customer_id = c.id
            WHERE b.id = ?
        """, (booking_id,))
        
        booking = cursor.fetchone()
        conn.close()
        
        if not booking:
            return False, None, f"Booking ID #{booking_id} not found in system."
            
        if booking["status"] == "Cancelled":
            return False, None, f"Booking #{booking_id} is already cancelled."

        return True, dict(booking), f" Verified Invoice for Booking #{booking_id}."

    except Exception as e:
        return False, None, f"Verification Error: {e}"

# --- UPDATED: SEND CANCELLATION EMAIL ---
def send_cancellation_email(to_email, name, booking_id):
    if "your_email" in config.SENDER_EMAIL:
        return True # Sim

    try:
        msg = MIMEMultipart()
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Cancellation Confirmed: Booking #{booking_id}"
        
        body = f"""
        Hi {name},
        
        Your booking #{booking_id} has been successfully cancelled as per your request.
        
        If a refund is applicable based on our policy (uploaded invoice verified), it will be processed within 5-7 days.
        
        Regards,
        Scout AI Team
        """
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        server.sendmail(config.SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except: return False

    # --- NEW TOOL: UPDATE BOOKING IN DB ---
def update_booking_details(booking_id, new_date, new_guests, new_total):
    """
    Updates the date, guests, and total cost for an existing booking.
    """
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        # We also update the booking_date string to show the new range if needed
        # For simplicity, we just update the start date field here, 
        # or you can re-calculate the full range string "Start to End" if you tracked nights.
        
        cursor.execute("""
            UPDATE bookings 
            SET booking_date = ?, guest_count = ?
            WHERE id = ?
        """, (new_date, new_guests, booking_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Update DB Error: {e}")
        return False

# --- NEW TOOL: SEND UPDATE EMAIL ---
def send_update_email(to_email, name, booking_id, old_details, new_details):
    if "your_email" in config.SENDER_EMAIL:
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Booking Updated: #{booking_id} - Scout AI"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="padding: 20px; background-color: #f4f4f4;">
                <div style="background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #1B4D3E;">Booking Updated Successfully </h2>
                    <p>Hi <strong>{name}</strong>,</p>
                    <p>Your booking <strong>#{booking_id}</strong> has been modified as requested.</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f2f2f2;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Detail</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Old Value</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>New Value</strong></td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;">Date</td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{old_details['date']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>{new_details['date']}</strong></td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;">Guests</td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{old_details['guests']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>{new_details['guests']}</strong></td>
                        </tr>
                    </table>
                    
                    <p>We look forward to hosting you!</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        server.sendmail(config.SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False