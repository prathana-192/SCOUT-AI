# ⛺ Scout AI — Intelligent Camping Booking Assistant

**Scout AI** is a production-grade conversational booking agent designed to automate consultation and reservation processes for camping trips.  
It uses a **Hybrid Architecture** combining Unstructured Knowledge (RAG) with Structured Logic (State Machines) to reliably handle:

- Itinerary planning  
- Real-time availability checks  
- User-context understanding  
- Booking, updating, canceling  
- PDF invoice verification  

---

##  Key Features

###  1. Hybrid RAG Architecture ("The Brain")
- **Dual Knowledge System**  
  - Policy & safety answers through **PDF Documents** (FAISS Vector Store)  
  - Pricing, packages, and availability from **Structured JSON Logic**  
- **Query Rewriting**  
  Converts vague questions into specific intents  
  > "How much is it *there*?" → "How much is it in *Coorg*?"

---

###  2. Context-Aware Booking Engine ("The Manager")
- **Hybrid Context Scanner**  
  Remembers user preferences across chat turns (location, guests, dates).
- **Stateful Conversations**  
  Manages Booking → Update → Cancel workflows reliably.
- **Partial Updates**  
  Users can modify only specific fields  
  > e.g., “Change the date” without re-entering all details.

---

###  3. Verification & Safety ("The Bouncer")
- **Invoice Verification via OCR**  
  Validates uploaded **PDF invoices** against the database.
- **Atomic Transactions**  
  Booking is saved *only* after successful confirmation email delivery.  
  If email fails → automatic rollback.

---

###  4. Admin Dashboard
- Revenue insights  
- Booking trends  
- Manage/update bookings  
- Export booking data as CSV

---

###  5. Interactive UI
- **Clickable Availability Table**  
  Users select dates/packages without typing.
- Fully built with **Streamlit**.

---

##  Tech Stack

- **Frontend:** Streamlit  
- **LLM Engine:** Groq (Llama 3.1 8B/70B)  
- **Embeddings:** FastEmbed (local CPU)  
- **Vector Store:** FAISS  
- **Database:** SQLite  
- **Email:** SMTP (Gmail App Password)  
- **OCR:** PyMuPDF / Tesseract (depending on your setup)

---

##  Project Structure

```text
scout-ai/
├── app/
│   ├── main.py              # UI & Router
│   ├── booking_flow.py      # State Machine & Context Logic
│   ├── rag_pipeline.py      # PDF Ingestion + Vector Retrieval
│   ├── tools.py             # Email, DB, OCR, Utils
│   ├── admin_dashboard.py   # Admin Panel UI
│   └── data/                # Pricing, Logistics, JSON rules
├── config/
│   └── config.py            # Environment Variables
├── db/                      # Auto-generated SQLite DB
├── docs/                    # PDF Knowledge Base (Coorg, Wayanad, Policies)
├── assets/                  # Images, Branding
├── requirements.txt
└── README.md
```

---

##  Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/prathana-192/scout-ai.git
cd scout-ai
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
python setup_db.py
```

### 4. Configure Secrets

Create a `.env` file:

```ini
# Groq API
GROQ_API_KEY="gsk_your_api_key"

# Gmail SMTP (Use App Password)
SENDER_EMAIL="your_email@gmail.com"
SENDER_PASSWORD="your_gmail_app_password"
```

### 5. Run the Application

```bash
streamlit run app/main.py
```

---

##  Usage Guide

###  User Flow

1. Ask:  
   - “Tell me about Coorg”  
   - “Can I bring my dog?”  
   - “What’s the food menu?”  
2. Say: **“Book this”**  
3. Select date & package using the **Interactive Table**  
4. Confirm booking → Receive **HTML email invoice**

---

###  Update / Cancel Flow

1. Say: **“I want to update my booking.”**  
2. Upload your **PDF Invoice**  
3. Bot verifies Booking ID  
4. Modify fields:  
   - “Change date”  
   - “Increase guest count”  
5. Bot recalculates + updates DB

---

###  Admin Flow

1. Open **Admin Dashboard** from sidebar  
2. View analytics & booking history  
3. Export CSV  
4. Modify booking statuses

---

##  Advanced Logic (Under the Hood)

Scout AI uses a **Deterministic State Machine**:

1. User input → Intent Mapping  
2. Fuzzy match to location keys (`coorg`, `wayanad`)  
3. Availability Check  
4. Price calculation (Python, not LLM)  
5. Strict JSON payload → Database insert/update  

---

##  Future Improvements

- Voice Interface (TTS + STT)  
- Payment Gateway (Stripe / Razorpay)  
- User Login & Booking History  

---

##  Contributing

Pull requests are welcome!  
For major changes, please open an issue first.

---

##  License

MIT License – feel free to use and modify.

