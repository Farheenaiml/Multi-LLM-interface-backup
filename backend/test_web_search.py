import asyncio
from dotenv import load_dotenv
from web_search import search_web

# Load environment variables from .env
load_dotenv()

async def test_search():
    print("Testing Tavily web search integration...")
    query = "What is FastAPI?"
    print(f"Query: {query}")
    
    try:
        results = await search_web(query)
        if results:
            print(f"\nFound {len(results)} results:\n")
            for idx, result in enumerate(results, start=1):
                print(f"{idx}. Title: {result['title']}")
                print(f"   URL: {result['url']}")
                print(f"   Content Snippet: {result['content'][:150]}...\n")
        else:
            print("\nNo results returned or an error occurred.")
            
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
    except Exception as e:
        print(f"\nUnexpected Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
