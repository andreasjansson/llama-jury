import asyncio
import re
from typing import List, Tuple, Optional, Dict, Any
import replicate

from monkey_patch_replicate import monkey_patch_replicate
monkey_patch_replicate(replicate)


MAX_ATTEMPTS = 8


async def gen(prompt) -> str:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, gen_sync, prompt)
    return result


def gen_sync(prompt, *, attempt=0) -> str:
    try:
        output = replicate.run(
            "a16z-infra/llama-2-13b-chat:2a7f981751ec7fdf87b5b91ad4db53683a98082e9ff7bfd12c8cd5ea85980a52",
            # "replicate/llama-2-70b-chat:58d078176e02c219e11eb4da5a02a7830a283b14cf8f94537af893ccff5ee781",
        input={"prompt": prompt, "system_prompt": "", "temperature": 1.1},
        )
        output = "".join(list(output)).strip()
    except Exception:
        if attempt > 3:
            raise
        return gen_sync(prompt, attempt=attempt + 1)

    # Catch "as a language model", etc.
    if " AI " in output or "language model" in output.lower():
        if attempt > 5:
            return ""
        return gen_sync(prompt, attempt=attempt + 1)

    return output


async def gen_formatted_response(prompt, response_fields):
    for _ in range(MAX_ATTEMPTS):
        output = await gen(prompt)
        parsed = parse_formatted_response(output, response_fields)
        if parsed is not None:
            return parsed
    return None


def parse_formatted_response(
    text: str, fields: List[Tuple[str, type]]
) -> Optional[Dict[str, Any]]:
    parsed_data = {}
    for field, data_type in fields:
        # Use regular expressions to find the data associated with each field
        pattern = rf"{field}:(?:\n )*(.*?)($|\n(?=[A-Z_]+:|\Z))"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            # If the field is found, attempt to cast it to the specified data type
            try:
                parsed_data[field] = data_type(match.group(1).strip())
            except ValueError:
                return None
        else:
            return None

    return parsed_data


def fuzzy_percent(s):
    # Remove unnecessary white spaces
    s = s.strip()

    # Use a regular expression to search for a number, optionally followed by a percent sign
    match = re.search(r"\b(\d+(\.\d+)?)%?\b", s)
    if match:
        # If a match is found, convert the first group to an integer and return it
        return int(float(match.group(1)))
    else:
        # If no match is found, return None
        return None


def response_format_prompt(fields):
    lines = []
    for key, _ in fields:
        lines.append(key + ":")
    return "\n\n".join(lines)
