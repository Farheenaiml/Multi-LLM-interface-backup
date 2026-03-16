import asyncio
import httpx
import os

async def main():
    base_url = "http://localhost:5000"
    
    print("1. Creating a dummy document...")
    with open("dummy_leave_policy.txt", "w") as f:
        f.write("Company Leave Policy for 2024:\n")
        f.write("All employees are entitled to 20 days of paid time off per year. ")
        f.write("Sick leave is capped at 10 days per year. ")
        f.write("Maternity leave is 16 weeks, and paternity leave is 4 weeks. ")
        f.write("To request leave, please submit a form to the HR portal at least 2 weeks in advance.\n")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("\n2. Uploading document...")
            with open("dummy_leave_policy.txt", "rb") as f:
                files = {"file": ("dummy_leave_policy.txt", f, "text/plain")}
                r = await client.post(f"{base_url}/upload-document", files=files)
                print(f"Upload Response ({r.status_code}): {r.text}")

            print("\n3. Testing Private Search...")
            search_payload = {"query": "How many days of sick leave do I get?", "top_k": 3}
            r = await client.post(f"{base_url}/search-private", json=search_payload)
            print(f"Search Response ({r.status_code}): {r.text}")

            print("\n4. Testing Full RAG Query...")
            rag_payload = {
                "query": "How many weeks of paternity leave are allowed?",
                "model_id": "google/gemini-2.5-flash"
            }
            r = await client.post(f"{base_url}/rag-query", json=rag_payload)
            print(f"RAG Query Response ({r.status_code}): {r.text}")

    finally:
        if os.path.exists("dummy_leave_policy.txt"):
            os.remove("dummy_leave_policy.txt")

if __name__ == "__main__":
    asyncio.run(main())
