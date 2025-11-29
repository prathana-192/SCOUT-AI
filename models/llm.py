import os
import sys
from langchain_groq import ChatGroq

# Add parent directory to path to import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config

def get_chatgroq_model():
    """Initialize and return the Groq chat model using settings from config"""
    try:
        if not config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is missing in config.py!")

        # Initialize the Groq chat model
        groq_model = ChatGroq(
            api_key=config.GROQ_API_KEY,
            model_name=config.GROQ_MODEL_NAME,
            temperature=0.3 # Lower temperature for more factual answers
        )
        return groq_model
    except Exception as e:
        print(f"Error initializing Groq: {e}")
        return None