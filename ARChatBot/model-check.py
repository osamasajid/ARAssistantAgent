import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load your API key from the .env file
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Available Models for your API Key:")
print("-" * 30)

# Query the API to list all models that support generating text
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)