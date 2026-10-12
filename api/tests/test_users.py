import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.database import session_factory
from src.modules.auth.models import User
from src.modules.auth.schemas import UserRead
from tests.helpers import PASSWORD, auth_headers


async def _get_user(user_id: uuid.UUID) -> User:
    async with session_factory() as session:
        return (await session.scalars(select(User).where(User.id == user_id))).one()


async def test_superuser_creates_regular_user_who_can_log_in(
    client: AsyncClient, superuser: UserRead, superuser_headers: dict[str, str]
):
    response = await client.post(
        "/v1/users", json={"email": "New.Operator@Example.com", "password": PASSWORD}, headers=superuser_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.operator@example.com"
    assert body["is_superuser"] is False
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body

    stored = await _get_user(uuid.UUID(body["id"]))
    assert stored.created_by_id == superuser.id
    assert stored.password_hash.startswith("$argon2id$")

    await auth_headers(client, "new.operator@example.com")


async def test_duplicate_email_is_a_conflict(
    client: AsyncClient, regular_user: UserRead, superuser_headers: dict[str, str]
):
    response = await client.post(
        "/v1/users", json={"email": "OPERATOR@example.com", "password": PASSWORD}, headers=superuser_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_short_password_is_rejected(client: AsyncClient, superuser_headers: dict[str, str]):
    response = await client.post(
        "/v1/users", json={"email": "a@example.com", "password": "short"}, headers=superuser_headers
    )

    assert response.status_code == 422


async def test_superuser_lists_users(client: AsyncClient, regular_user: UserRead, superuser_headers: dict[str, str]):
    response = await client.get("/v1/users", headers=superuser_headers)

    assert response.status_code == 200
    assert [user["email"] for user in response.json()] == ["root@example.com", "operator@example.com"]

    second_page = await client.get("/v1/users", params={"limit": 1, "offset": 1}, headers=superuser_headers)
    assert [user["email"] for user in second_page.json()] == ["operator@example.com"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/v1/users", {"email": "x@example.com", "password": PASSWORD}),
        ("GET", "/v1/users", None),
        ("PATCH", "/v1/users/{superuser_id}", {"is_active": False}),
    ],
    ids=["create", "list", "update"],
)
async def test_regular_user_cannot_manage_users(
    client: AsyncClient,
    superuser: UserRead,
    regular_headers: dict[str, str],
    method: str,
    path: str,
    body: dict | None,
):
    response = await client.request(method, path.format(superuser_id=superuser.id), json=body, headers=regular_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert (await _get_user(superuser.id)).is_active


async def test_deactivated_user_loses_access_immediately_and_cannot_log_in(
    client: AsyncClient, regular_user: UserRead, regular_headers: dict[str, str], superuser_headers: dict[str, str]
):
    response = await client.patch(f"/v1/users/{regular_user.id}", json={"is_active": False}, headers=superuser_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # The token issued before deactivation stops working on the next request.
    assert (await client.get("/v1/auth/me", headers=regular_headers)).status_code == 401
    login = await client.post("/v1/auth/token", json={"email": regular_user.email, "password": PASSWORD})
    assert login.status_code == 401

    await client.patch(f"/v1/users/{regular_user.id}", json={"is_active": True}, headers=superuser_headers)
    await auth_headers(client, regular_user.email)


async def test_password_reset_revokes_existing_tokens(
    client: AsyncClient, regular_user: UserRead, regular_headers: dict[str, str], superuser_headers: dict[str, str]
):
    new_password = "a-brand-new-password"
    response = await client.patch(
        f"/v1/users/{regular_user.id}", json={"password": new_password}, headers=superuser_headers
    )
    assert response.status_code == 200

    assert (await client.get("/v1/auth/me", headers=regular_headers)).status_code == 401
    old_login = await client.post("/v1/auth/token", json={"email": regular_user.email, "password": PASSWORD})
    assert old_login.status_code == 401
    new_headers = await auth_headers(client, regular_user.email, new_password)
    assert (await client.get("/v1/auth/me", headers=new_headers)).status_code == 200


async def test_superuser_cannot_deactivate_themselves(
    client: AsyncClient, superuser: UserRead, superuser_headers: dict[str, str]
):
    response = await client.patch(f"/v1/users/{superuser.id}", json={"is_active": False}, headers=superuser_headers)

    assert response.status_code == 403
    assert (await _get_user(superuser.id)).is_active


async def test_updating_unknown_user_is_not_found(client: AsyncClient, superuser_headers: dict[str, str]):
    response = await client.patch(f"/v1/users/{uuid.uuid4()}", json={"is_active": False}, headers=superuser_headers)

    assert response.status_code == 404
