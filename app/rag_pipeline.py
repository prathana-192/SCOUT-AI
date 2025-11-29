import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config.config as config
import models.llm as llm

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 1. SETUP EMBEDDINGS
def get_embedding_model():
    return FastEmbedEmbeddings(model_name=config.EMBEDDING_MODEL)

# 2. INITIALIZE KNOWLEDGE BASE (Same as before)
def initialize_knowledge_base():
    if os.path.exists(config.VECTOR_DB_PATH):
        print(f"Knowledge Base found at {config.VECTOR_DB_PATH}")
        return

    print("Building Knowledge Base from ALL PDFs in docs/...")
    all_docs = []
    docs_folder = os.path.join(config.BASE_DIR, "docs")
    
    if not os.path.exists(docs_folder):
        print(" Docs folder not found!")
        return

    for filename in os.listdir(docs_folder):
        if filename.endswith(".pdf"):
            file_path = os.path.join(docs_folder, filename)
            loader = PyPDFLoader(file_path)
            all_docs.extend(loader.load())

    if not all_docs: return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(all_docs)

    embeddings = get_embedding_model()
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(config.VECTOR_DB_PATH)
    print(" Knowledge Base Built!")

# 3. ADD USER PDF (Same as before)
def add_user_pdf_to_db(uploaded_file):
    try:
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        loader = PyPDFLoader(temp_path)
        docs = loader.load()
        os.remove(temp_path)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        new_chunks = text_splitter.split_documents(docs)

        embeddings = get_embedding_model()
        if os.path.exists(config.VECTOR_DB_PATH):
            vector_store = FAISS.load_local(config.VECTOR_DB_PATH, embeddings, allow_dangerous_deserialization=True)
            vector_store.add_documents(new_chunks)
        else:
            vector_store = FAISS.from_documents(new_chunks, embeddings)
        
        vector_store.save_local(config.VECTOR_DB_PATH)
        return "Document added to knowledge base!"
    except Exception as e:
        return f"Error adding document: {e}"

# 4. NEW HELPER: QUERY REWRITER
def rewrite_query(user_query, chat_history):
    """
    Uses LLM to rewrite "How much is it?" -> "How much is Kodaikanal Glamping?"
    """
    groq = llm.get_chatgroq_model()
    
    # If no history, no need to rewrite
    if not chat_history:
        return user_query

    # Convert last 3 messages to text for context
    history_text = ""
    for msg in chat_history[-3:]:
        role = "User" if msg["role"] == "user" else "Bot"
        history_text += f"{role}: {msg['content']}\n"

    system_prompt = f"""
    You are a Query Refiner. 
    Rewrite the User's last question to be STANDALONE, replacing pronouns (it, that, there) with the specific Location or Activity mentioned in the history.
    
    Chat History:
    {history_text}
    
    User Question: {user_query}
    
    Output ONLY the rewritten question. Do not answer it.
    """
    
    try:
        response = groq.invoke([SystemMessage(content=system_prompt)])
        return response.content.strip()
    except:
        return user_query

# 5. CONVERSATIONAL SEARCH (Updated)
def query_rag(query_text, chat_history=[]):
    if not os.path.exists(config.VECTOR_DB_PATH):
        return "I don't have a knowledge base yet."

    try:
        # A. REWRITE QUERY (The Fix)
        # We search the PDF using the "Smart Query", not the "Lazy User Query"
        search_query = rewrite_query(query_text, chat_history)
        print(f"🔍 Searching PDF for: '{search_query}'") # Debug print to see it working

        # B. Retrieve Context
        embeddings = get_embedding_model()
        vector_store = FAISS.load_local(config.VECTOR_DB_PATH, embeddings, allow_dangerous_deserialization=True)
        docs = vector_store.similarity_search(search_query, k=3) # Use search_query here!
        context_text = "\n\n".join([doc.page_content for doc in docs])

        # C. Generate Answer
        groq = llm.get_chatgroq_model()
        system_prompt = f"""
        You are Scout AI. Answer based on the CONTEXT below.
        
        CONTEXT:
        {context_text}
        
        RULES:
        1. Answer naturally.
        2. If context mentions "Module B: Cloud Farm", and user asks about "Glamping", connect them.
        3. Be honest about policies (No alcohol in forests).
        """

        messages = [SystemMessage(content=system_prompt)]
        for msg in chat_history[-5:]: 
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=query_text))

        response = groq.invoke(messages)
        return response.content

    except Exception as e:
        print(f"RAG Error: {e}")
        return "I'm having trouble thinking right now."

if __name__ == "__main__":
    initialize_knowledge_base()