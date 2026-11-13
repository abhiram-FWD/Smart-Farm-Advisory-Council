
import os
from dotenv import load_dotenv
from openai import OpenAI

# Load credentials from .env
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in .env")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1"
)

response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": "You are an agricultural advisory assistant."
        },
        {
            "role": "user",
            "content": "Explain in three points why soil moisture is important for wheat cultivation."
        }
    ],
    temperature=0.3
)

print("\nGROQ AI RESPONSE")
print("================")
print(response.choices[0].message.content)
