from ollama import Client, ChatResponse

client = Client(host='http://host.docker.internal:11434')

def analyze_chunk_with_ollama(chunk: str, document_type: str = "nda", language: str = "ru") -> ChatResponse:
    prompt = f"""
document_type: {document_type}
language: {language}

chunk:
\"\"\"
{chunk}
\"\"\"
"""
    response: ChatResponse = client.chat(
        model="legal-ai",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response
