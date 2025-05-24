from google import genai
from os import environ

from google.genai import types

# from google.genai import types

ACCOUNT_NUMBER = 0
ACCOUNT_PREFIX = "GEMINI_API_KEY"

OCR_MODELS = {
    "gemini-2.5-flash-preview-05-20": {"rpm": 10, "rpd": 500},
    "gemini-2.5-flash-preview-04-17": {"rpm": 10, "rpd": 500},
    "gemini-2.0-flash": {"rpm": 30, "rpd": 1500},
}
EMBEDDING_MODELS = {"sf": 323}

curr_account_number = 0
client: None | genai.Client = None


def setup_gemini(min_accounts=1):
    global ACCOUNT_NUMBER, ACCOUNT_PREFIX, client, curr_account_number

    for i in range(10):
        if environ.get(ACCOUNT_PREFIX + str(i + 1)):
            ACCOUNT_NUMBER += 1
    if ACCOUNT_NUMBER < min_accounts:
        raise Exception(
            f"you wanted {min_accounts}, but you only provided api-key for {ACCOUNT_NUMBER} !!"
        )

    account_nr = (curr_account_number % ACCOUNT_NUMBER) + 1
    account_key = f"{ACCOUNT_PREFIX}{account_nr}"
    client = genai.Client(api_key=environ.get(account_key))


def switch_account():
    global ACCOUNT_NUMBER, ACCOUNT_PREFIX, client, curr_account_number
    curr_account_number += 1

    account_nr = (curr_account_number % ACCOUNT_NUMBER) + 1
    account_key = f"{ACCOUNT_PREFIX}{account_nr}"
    client = genai.Client(api_key=environ.get(account_key))


def ocr_a_question(q_img_path: str, model: str):
    global client, OCR_PROMPT

    if model not in OCR_MODELS:
        raise Exception()

    file = client.files.upload(file=q_img_path)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=OCR_PROMPT),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
    )

    response = client.models.generate_content(
        model=model,
        contents=["Could you summarize this file?", file],
        config=generate_content_config,
    )


def create_embedding(text: str, model) -> list:
    result = client.models.embed_content().embed_content(
        model="models/text-embedding-004", content=text
    )["embedding"]
    return result


OCR_PROMPT = """




"""
