import re
import time
import os
import openai

async def generate(prompt) -> str:
    openai.api_key = os.environ["OPENAI_API_KEY"]
    response = await openai.ChatCompletion.acreate(
        model="gpt-4",
        messages=[
            {
                "role": "user",
                "content": prompt,
            },
        ],
        n=1,
        stop=None,
        temperature=0.7,
        stream=False,
    )
    output = response["choices"][0]["message"]["content"]
    return output
