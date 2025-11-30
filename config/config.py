import os
from dotenv import load_dotenv

load_dotenv()


# 1. API KEYS
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 

# 2. MODEL SETTINGS
GROQ_MODEL_NAME = "llama-3.3-70b-versatile" 
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  

# 3. PATHS
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, "db", "camping.db")
PDF_PATH = os.path.join(BASE_DIR, "docs", "Camping_Guide.pdf")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "faiss_index")

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# 5. SUPABASE CREDENTIALS
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")