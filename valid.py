import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

models = genai.list_models()

for model in models:
    print(f"Model name: {model.name}")
    print(f"Supported generation methods: {model.supported_generation_methods}\n")
