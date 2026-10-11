import os
from dotenv import load_dotenv

load_dotenv()
provider = os.getenv("MODEL_PROVIDER")
model = os.getenv("MODEL_NAME")
key = os.getenv("API_KEY")

if not (provider and model and key):
    raise SystemExit("Missing MODEL_PROVIDER, MODEL_NAME or API_KEY in .env")

prompt = "Say hello in one short sentence."

if provider == "google":
    from google import genai
    client = genai.Client(api_key=key)
    reply = client.models.generate_content(model=model, contents=prompt).text
elif provider == "anthropic":
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    reply = client.messages.create(
        model=model, max_tokens=50,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text
elif provider == "openai":
    from openai import OpenAI
    client = OpenAI(api_key=key)
    reply = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
else:
    raise SystemExit(f"Unknown provider: {provider}")

print("OK:", reply)
