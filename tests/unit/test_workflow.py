import pytest

from netbox_readwrite_mcp.workflow import Workflow
from netbox_readwrite_mcp.catalog import api_path, query_string
from netbox_readwrite_mcp.api import multipart
from netbox_readwrite_mcp.web import Page, Website


def test_interpreter_loops_conditionals_aggregation_and_calls():
    calls = []

    def call(name, **args):
        calls.append((name, args))
        return {"values": [1, 2, 3]}

    source = """
data = tool("read", count=1)
items = []
for x in data["values"]:
    if x > 1 and x < 4:
        items.append(x * 2)
result = {"sum": sum(items), "n": len(items), "get": data.get("absent", 0)}
"""
    assert Workflow(call).run(source) == {"sum": 10, "n": 2, "get": 0}
    assert calls == [("read", {"count": 1})]


@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "from os import environ",
        "result = __import__('os')",
        "result = open('/etc/passwd')",
        "result = (1).__class__",
        "result = tool.__globals__",
        "while True: pass",
        "def f(): pass",
        "class X: pass",
        "result = lambda: 1",
        "result = [x for x in range(10)]",
        "result = range(1001)",
        "result = 'a' * 999999999",
        "result = '%999999999s' % 'x'",
        "result = 2 ** 999999999",
        "result = tool(**{})",
        "_secret = 1",
        "result = []\nresult.append(result)\nresult = result + []",
        "for x in range(1000):\n    for y in range(1000):\n        result = x + y",
    ],
)
def test_interpreter_rejects_host_access_and_unbounded_work(source):
    with pytest.raises((ValueError, KeyError)):
        Workflow(lambda *a, **kw: {}).run(source)


def test_static_rejection_before_any_tool_call():
    calls = []
    with pytest.raises(ValueError):
        Workflow(lambda *a: calls.append(a)).run('tool("write")\nimport os')
    assert calls == []


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("1 + 2 - 1", 2),
        ("4 / 2", 2),
        ("5 % 2", 1),
        ("-1", -1),
        ("+1", 1),
        ("not False", True),
        ("1 == 1 != 2", True),
        ("1 >= 1", True),
        ("1 <= 2", True),
        ("1 in [1]", True),
        ("2 not in [1]", True),
        ("None is None", True),
        ("1 is not None", True),
        ("False or True", True),
        ("False and True", False),
        ("sorted([3, 1, 2])", [1, 2, 3]),
        ("min([1,2])", 1),
        ("max([1,2])", 2),
        ('str(int("2"))', "2"),
        ('{"a": 1}.keys()', ["a"]),
        ('{"a": 1}.values()', [1]),
        ('{"a": 1}.items()', [("a", 1)]),
    ],
)
def test_workflow_expressions(expression, expected):
    assert Workflow(None).run("result = " + expression) == expected


@pytest.mark.parametrize(
    "path",
    [
        "https://evil/",
        "/dcim/devices/",
        "dcim/../users/",
        "dcim/%2e%2e/",
        "dcim/devices/?q=x",
        "dcim/devices",
    ],
)
def test_api_paths_are_local_and_explicit(path):
    with pytest.raises(ValueError):
        api_path(path)


def test_query_and_multipart():
    assert query_string({"x": [1, 2], "enabled": True}) == "x=1&x=2&enabled=true"
    with pytest.raises(ValueError):
        query_string({"x": {}})
    with pytest.raises(ValueError):
        query_string({"x": [{}]})
    raw, content_type = multipart(
        {"names": ["a", "b"]}, [{"field": "file", "filename": "a.txt", "base64": "aGk="}]
    )
    assert b"hi" in raw and "multipart/form-data" in content_type
    for name in ["x\r\nInjected: yes", "../secret", 'a"b']:
        with pytest.raises(ValueError):
            multipart({}, [{"field": "file", "filename": name, "base64": ""}])


def test_html_forms_are_data_and_secrets_are_not_returned():
    page = Page(
        '<script>evil()</script><form method="post"><input name="csrfmiddlewaretoken" value="secret"><input type="password" value="secret"><input name="name" value="router"><select name="status"><option value="active" selected>Active</option></select></form><a href="/dcim/">DCIM</a>'
    )
    assert "secret" not in str(page.forms)
    assert "evil()" not in page.text
    assert page.forms[0]["fields"][2]["value"] == "router"
    assert page.links == ["/dcim/"]


@pytest.mark.parametrize(
    "path", ["https://evil/", "//evil/", "/a/../b/", "/%2e%2e/", "/a\\b/", "/foo#fragment"]
)
def test_website_stays_on_origin(path):
    api = type("API", (), {"url": "https://netbox.example"})()
    with pytest.raises(ValueError):
        Website(api, "agent", None).url(path)


def test_website_prefix_is_transparent_to_agent_paths():
    api = type("API", (), {"url": "https://netbox.example/netbox"})()
    web = Website(api, "agent", None)
    assert web.url("/dcim/sites/") == "https://netbox.example/netbox/dcim/sites/"
    assert web.url("/netbox/dcim/sites/") == "https://netbox.example/netbox/dcim/sites/"
