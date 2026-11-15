import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from agents.evidence import InvalidModelOutputError

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _configuration():
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")
    if not api_key or not model:
        raise RuntimeError("Groq API credentials or model configuration are unavailable.")
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL), model


def ask_groq(system_prompt, user_prompt):
    client, model = _configuration()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content


def ask_groq_json(system_prompt, user_prompt):
    client, model = _configuration()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.2
    )

    content = response.choices[0].message.content

    try:
        result = json.loads(content)
    except (json.JSONDecodeError, TypeError) as error:
        raise InvalidModelOutputError("The model response was not valid JSON.") from error
    if not isinstance(result, dict):
        raise InvalidModelOutputError("The model response must be a JSON object.")
    return result
