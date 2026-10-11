import os
import sys
import base64
import mimetypes
from dotenv import load_dotenv

load_dotenv()

PROMPT = (
    "This is an electricity bill image. Names, addresses and ID numbers are "
    "covered with grey boxes. In plain text, tell me: the provider, the bill "
    "month, the units consumed, the sanctioned load, the due date, the total "
    "charges, the taxes, and the amount payable within and after the due date. "
    "Say 'not visible' for anything you cannot read. Do not guess."
)


def load_image(path):
    mime = mimetypes.guess_type(path)[0]
    if mime not in ("image/png", "image/jpeg"):
        raise ValueError("Image must be .png or .jpg")
    with open(path, "rb") as f:
        return f.read(), mime


def call_google(model, key, data, mime, prompt, json_mode=False):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    cfg = {"temperature": 0, "max_output_tokens": 8000}
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    resp = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt],
        config=types.GenerateContentConfig(**cfg),
    )
    return resp.text


def call_anthropic(model, key, data, mime, prompt, json_mode=False):
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model, max_tokens=1500, temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": mime,
                "data": base64.b64encode(data).decode()}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return resp.content[0].text


def call_openai(model, key, data, mime, prompt, json_mode=False):
    from openai import OpenAI
    client = OpenAI(api_key=key)
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    kwargs = {} if model.startswith("gpt-5") else {"temperature": 0}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
        **kwargs,
    )
    return resp.choices[0].message.content


PROVIDERS = {"google": call_google, "anthropic": call_anthropic, "openai": call_openai}


def call_model(image_path, prompt=PROMPT, json_mode=False):
    provider = os.getenv("MODEL_PROVIDER")
    model = os.getenv("MODEL_NAME")
    key = os.getenv("API_KEY")
    if not (provider and model and key):
        raise RuntimeError("Set MODEL_PROVIDER, MODEL_NAME and API_KEY in .env")
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown MODEL_PROVIDER: {provider}")
    data, mime = load_image(image_path)
    return PROVIDERS[provider](model, key, data, mime, prompt, json_mode)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python extract.py path/to/bill.png")
    if not os.path.exists(sys.argv[1]):
        sys.exit(f"File not found: {sys.argv[1]}")
    try:
        print(call_model(sys.argv[1]))
    except Exception as e:
        sys.exit(f"Error: {e}")