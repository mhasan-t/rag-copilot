import pytest
from httpx import AsyncClient

from src.core.exceptions import ConflictError
from src.modules.auth.cli import create_superuser
from src.modules.auth.schemas import UserRead
from tests.helpers import PASSWORD, auth_headers


async def test_cli_created_superuser_can_log_in_and_see_themselves(client: AsyncClient, superuser: UserRead):
    response = await client.post("/v1/auth/token", json={"email": superuser.email, "password": PASSWORD})

    assert response.status_code == 200
    token = response.json()
    assert token["token_type"] == "bearer"
    assert token["expires_in"] == 3600

    me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "root@example.com"
    assert me.json()["is_superuser"] is True


async def test_login_email_is_case_insensitive(client: AsyncClient, superuser: UserRead):
    await auth_headers(client, "ROOT@Example.com")


async def test_cli_rejects_duplicate_email(superuser: UserRead):
    with pytest.raises(ConflictError):
        await create_superuser("Root@example.com", PASSWORD)


@pytest.mark.parametrize(
    ("email", "password"),
    [("root@example.com", "wrong-password-123"), ("nobody@example.com", PASSWORD)],
    ids=["wrong-password", "unknown-email"],
)
async def test_failed_login_does_not_reveal_which_part_was_wrong(
    client: AsyncClient, superuser: UserRead, email: str, password: str
):
    response = await client.post("/v1/auth/token", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "unauthorized",
        "message": "Invalid email or password",
        "details": None,
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic cm9vdDpwYXNz"}],
    ids=["no-header", "garbage-token", "wrong-scheme"],
)
@pytest.mark.parametrize(("method", "path"), [("GET", "/v1/auth/me"), ("GET", "/v1/users"), ("POST", "/v1/users")])
async def test_protected_routes_reject_unauthenticated_requests(
    client: AsyncClient, headers: dict[str, str], method: str, path: str
):
    response = await client.request(method, path, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_health_stays_public(client: AsyncClient):
    assert (await client.get("/v1/health")).status_code == 200
