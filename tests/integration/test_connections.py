"""Native account-link disconnection, stale state, ownership and last-login guard."""

import os

import pytest

from netbox_readwrite_mcp.api import NetBox
from scripts.lab import URL
from tests.integration.test_personal import people  # noqa: F401
from tests.integration.test_configuration import shell

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("NETBOX_RW_LIVE") != "1", reason="Disposable lab opt-in required"),
]
PATH = "plugins/agent-support/self/connections/"


def test_native_own_connections_and_last_login_protection(people):  # noqa: F811
    a, b = [entry[0] for entry in people]
    shell(f"""
from django.contrib.auth import get_user_model
from social_django.models import UserSocialAuth
for name in [{a.actor!r}, {b.actor!r}]:
    user = get_user_model().objects.get(username=name)
    user.set_unusable_password()
    user.save()
    for suffix in ['one', 'two']:
        UserSocialAuth.objects.create(user=user, provider='github', uid=name + suffix, extra_data={{'access_token': 'private-disposable-token'}})
""")
    state = a.api.get(PATH)["body"]
    other = b.api.get(PATH)["body"]
    assert len(state["results"]) == len(other["results"]) == 2
    assert "private-disposable-token" not in str(state)
    ids = [row["id"] for row in state["results"]]
    base = {"provider": "github", "expected": state["expected"]}
    assert a.api.request("POST", PATH, {**base, "id": other["results"][0]["id"]})["status"] == 404
    assert a.api.request("POST", PATH, base)["status"] == 400
    assert a.api.get(PATH)["body"] == state
    assert NetBox(URL, people[0][1]).request("POST", PATH, {**base, "id": ids[0]})["status"] == 403
    task = a.begin_task("Native identity association removal")["task_id"]
    result = a.execute_action(task, "disconnect-one", "POST", PATH, {**base, "id": ids[0]})
    assert result["last_receipt"]["status"] == 200 and result["state"] == "completed", result
    assert a.api.request("POST", PATH, {**base, "id": ids[1]})["status"] == 409
    current = a.api.get(PATH)["body"]
    assert len(current["results"]) == 1
    assert (
        a.api.request("POST", PATH, {"provider": "github", "expected": current["expected"]})["status"] == 400
    )
    shell(f"""
from django.contrib.auth import get_user_model
user = get_user_model().objects.get(username={a.actor!r})
user.set_password('disposable qualification password never published')
user.save()
""")
    removed = a.api.request("POST", PATH, {"provider": "github", "expected": current["expected"]})
    assert removed["status"] == 200 and removed["body"]["results"] == [], removed
    assert b.api.get(PATH)["body"] == other
