from httpx import AsyncClient

PASSWORD = "correct-horse-battery"


async def auth_headers(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/v1/auth/token", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
