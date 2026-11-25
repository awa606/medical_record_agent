from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from fastapi.testclient import TestClient

from app.main import app


class _WorkbenchAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "script" and attr.get("src"):
            self.urls.append(attr["src"])
        elif tag == "link" and attr.get("rel") == "stylesheet":
            self.urls.append(attr["href"])


def test_doctor_entry_delivers_current_shell_on_conditional_get_and_head():
    client = TestClient(app)
    path = "/static/doctor.html"
    first = client.get(path)
    assert first.status_code == 200
    for address in (path, path + "?v=existing-deployment"):
        current = client.get(address, headers={"If-None-Match": first.headers["etag"]})
        assert current.status_code == 200
        assert current.content == first.content
        assert current.headers["cache-control"] == "no-store"
        head = client.head(address)
        assert head.status_code == 200 and not head.content
        assert head.headers["content-length"] == str(len(current.content))
        assert head.headers["cache-control"] == "no-store"


def test_workbench_script_and_styles_have_content_versioned_urls():
    client = TestClient(app)
    page = client.get("/static/doctor.html")
    assets = _WorkbenchAssets()
    assets.feed(page.text)
    assert len(assets.urls) >= 4
    for url in assets.urls:
        response = client.get(urljoin(str(page.url), url))
        assert response.status_code == 200
        # Both Git line-ending conventions represent the same source revision.
        digest = sha256(response.content.replace(b"\r\n", b"\n")).hexdigest()
        assert parse_qs(urlsplit(url).query) == {"v": [digest[:16]]}, url
