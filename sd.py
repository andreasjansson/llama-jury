import asyncio
import replicate


async def make_image(agent) -> str:
    prompt = f"{agent.name}, {agent.mood}, facing the camera, photo, 1950s, neo noir, hyper-realism, kodachrome"

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, make_image_sync, prompt)
    return result


def make_image_sync(prompt, attempt=0) -> str:
    try:
        output = replicate.run(
            "stability-ai/sdxl:a00d0b7dcbb9c3fbb34ba87d2d5b46c56969c84a628bf778a7fdaec30b1b99c5",
            input={"prompt": prompt, "width": 512, "height": 1024},
        )
        return output[0]
    except replicate.exceptions.ModelError:
        if attempt > 3:
            return ""
        return make_image_sync(prompt, attempt + 1)
