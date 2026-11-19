import os
from dotenv import load_dotenv
load_dotenv(override=True)
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
msg = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=64,
    messages=[{"role": "user", "content": "Reply with just: OK"}],
)
print(msg.content[0].text)
