import asyncio
from web_search import should_search_web

async def test():
    prompt = "give todays news"
    result = await should_search_web(prompt)
    print(f"Prompt: '{prompt}'")
    print(f"Needs Search: {result}")

if __name__ == "__main__":
    asyncio.run(test())
