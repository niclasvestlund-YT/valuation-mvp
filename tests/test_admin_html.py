"""
tests/test_admin_html.py

Testar admin.html-strukturen statiskt och API-integrationen dynamiskt.
Kör: pytest tests/test_admin_html.py -v
"""

import re
import pytest
from pathlib import Path
from bs4 import BeautifulSoup

ADMIN_HTML = Path(__file__).resolve().parents[1] / "frontend" / "admin.html"


@pytest.fixture
def soup():
    return BeautifulSoup(ADMIN_HTML.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture
def js_code(soup):
    scripts = soup.find_all("script")
    return "\n".join(s.get_text() for s in scripts)


def _visible_text_without_scripts(html_path):
    """Return visible text with script/style tags removed."""
    s = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    for tag in s.find_all(["script", "style"]):
        tag.extract()
    return s.get_text()


# ── STRUKTUR ──────────────────────────────────────────────────────────────


class TestStructure:
    def test_file_exists(self):
        assert ADMIN_HTML.exists(), "frontend/admin.html måste finnas"

    def test_has_viewport_meta(self, soup):
        meta = soup.find("meta", {"name": "viewport"})
        assert meta, "Saknar viewport meta-tag"
        assert "width=device-width" in meta.get("content", "")

    def test_has_inter_font(self, soup):
        links = soup.find_all("link", rel=lambda r: r and "stylesheet" in r)
        hrefs = [l.get("href", "") for l in links]
        assert any("fonts.googleapis.com" in h and "Inter" in h for h in hrefs), \
            "Saknar Google Fonts Inter"

    def test_all_tabs_present(self, soup):
        required_ids = ["tab-ov", "tab-cr", "tab-vibe", "tab-eko", "tab-valor", "tab-hc"]
        for tab_id in required_ids:
            assert soup.find(id=tab_id), f"Saknar #{tab_id}"

    def test_no_real_api_names_in_visible_text(self):
        """Källnamnsabstraktion: Tradera, Blocket, Webhallen, Inet får inte synas i UI."""
        forbidden = ["Tradera", "Blocket", "Webhallen", "Inet.se", "Serper", "SerpAPI"]
        visible = _visible_text_without_scripts(ADMIN_HTML)
        for name in forbidden:
            assert name not in visible, \
                f"'{name}' syns i UI-text — ska vara abstraherat"

    def test_no_localStorage_usage(self, js_code):
        # localStorage is allowed ONLY for dark mode preference (dm key)
        import re
        # Remove all dark-mode localStorage calls, then check no other usage remains
        cleaned = re.sub(r"localStorage\.(set|get)Item\('dm'[^)]*\)", "", js_code)
        assert "localStorage" not in cleaned, \
            "Får inte använda localStorage utanför dark mode (säkerhetskrav)"
        assert "sessionStorage" not in js_code, \
            "Får inte använda sessionStorage"

    def test_esc_function_exists(self, js_code):
        assert "function esc(" in js_code, \
            "Saknar esc()-funktion för XSS-skydd"

    def test_copy_to_clipboard_exists(self, js_code):
        assert "copyToClipboard" in js_code, \
            "Saknar copyToClipboard-funktion"

    def test_render_error_function_exists(self, js_code):
        assert "renderError" in js_code, \
            "Saknar renderError-funktion"

    def test_no_hardcoded_version_in_html(self, soup):
        """Version must come from backend /health, not hardcoded in HTML."""
        title = soup.find("title").get_text()
        assert "v16" not in title and "v17" not in title, \
            "Title still has hardcoded version — should be 'Admin — Vardagsvärde'"
        meta = soup.find("meta", {"name": "build-version"})
        assert meta is None, "Hardcoded build-version meta tag should be removed"

    def test_build_info_populated_from_health(self, js_code):
        """build-info element should be populated from /health response data."""
        assert "build_sha" in js_code, \
            "Admin JS must read build_sha from /health to populate sidebar"

    def test_no_hardcoded_api_key(self, js_code):
        assert "sk-" not in js_code
        assert "Bearer " not in js_code

    def test_admin_key_not_in_url(self, js_code):
        assert "?key=" not in js_code
        assert "?admin_key=" not in js_code


# ── RESPONSIVITET ─────────────────────────────────────────────────────────


class TestResponsive:
    def test_has_media_query_640(self, soup):
        styles = "\n".join(s.get_text() for s in soup.find_all("style"))
        assert "640px" in styles, "Saknar media query vid 640px"

    def test_has_bottom_tab_bar(self, soup):
        tab_bar = soup.find(class_=re.compile(r"tab.bar|bottom.tab|mobile.nav", re.I))
        assert tab_bar or soup.find(id=re.compile(r"tab.bar|mobile.nav", re.I)), \
            "Saknar bottom tab bar för mobil"

    def test_max_width_760(self, soup):
        styles = "\n".join(s.get_text() for s in soup.find_all("style"))
        assert "760px" in styles, "Saknar max-width: 760px"


# ── EKONOMI-FLIK ──────────────────────────────────────────────────────────


class TestEkonomi:
    def test_three_subtabs_present(self, soup):
        tab = soup.find(id="tab-eko")
        assert tab, "Saknar #tab-eko"
        text = tab.get_text()
        assert "Prenumerationer" in text
        assert "API-användning" in text
        assert "Intäkter" in text

    def test_kpi_labels_not_too_long(self, soup):
        """KPI-labels ska max vara ett-två ord för att inte bryta rad."""
        tab = soup.find(id="tab-eko")
        if not tab:
            return
        kl_elements = tab.find_all(class_=re.compile(r"\bkl\b"))
        for el in kl_elements:
            text = el.get_text(strip=True)
            assert len(text) <= 20, \
                f"KPI-label för lång (kan bryta rad): '{text}'"

    def test_no_tab_label_breaks(self, soup):
        """Ekonomi-tabsen ska inte innehålla radbrytningar."""
        tab = soup.find(id="tab-eko")
        if not tab:
            return
        etabs = tab.find(class_=re.compile(r"etabs"))
        if etabs:
            for btn in etabs.find_all(class_=re.compile(r"\bet\b")):
                text = btn.get_text(strip=True)
                assert "\n" not in text


# ── VALOR ML ──────────────────────────────────────────────────────────────


class TestValorML:
    def test_valor_tab_exists(self, soup):
        assert soup.find(id="tab-valor"), "Saknar #tab-valor"

    def test_milestone_50_mentioned(self, soup):
        tab = soup.find(id="tab-valor")
        assert tab, "Saknar #tab-valor"
        assert "50" in tab.get_text(), "Milstolpe 50 saknas i Valor ML-fliken"

    def test_trained_state_conditional(self, js_code):
        """Tränat tillstånd ska vara villkorsstyrt, inte alltid synligt."""
        assert "model_available" in js_code or "trained" in js_code.lower(), \
            "Saknar villkor för tränat/ej tränat tillstånd"


# ── SYSTEMHÄLSA ───────────────────────────────────────────────────────────


class TestSystemHealth:
    def test_health_banner_exists(self, soup):
        ov = soup.find(id="tab-ov")
        assert ov, "Saknar #tab-ov"
        banner = ov.find(class_=re.compile(r"health.bar|health.banner", re.I))
        assert banner, "Saknar systemhälsa-banner på översikten"

    def test_halsokoll_tab_exists(self, soup):
        assert soup.find(id="tab-hc"), "Saknar #tab-hc (Hälsokoll)"


# ── CRAWLER ───────────────────────────────────────────────────────────────


class TestCrawler:
    def test_crawler_tab_exists(self, soup):
        assert soup.find(id="tab-cr"), "Saknar #tab-cr"

    def test_schema_or_schedule_referenced(self, soup):
        """Crawler-fliken ska referera till schema eller schemaläggning."""
        cr_tab = soup.find(id="tab-cr")
        if cr_tab:
            text = cr_tab.get_text().lower()
            assert "schema" in text or "ändra" in text or "schedule" in text, \
                "Saknar schema-referens i crawler-fliken"


# ── PRISASSISTENT ─────────────────────────────────────────────────────────


class TestPrisassistent:
    def test_assistant_section_on_overview(self, soup):
        ov = soup.find(id="tab-ov")
        assert ov, "Saknar #tab-ov"
        text = ov.get_text()
        assert "Prisassistent" in text or "assistant" in text.lower(), \
            "Saknar Prisassistent-sektion på översikten"

    def test_assistant_handles_missing_endpoint(self, js_code):
        """Frontend ska hantera att /admin/assistant-stats kan saknas."""
        assert "assistant-stats" in js_code, \
            "Saknar fetch mot /admin/assistant-stats"
        assert "catch" in js_code or "error" in js_code.lower(), \
            "Saknar felhantering för assistant-stats"


# ── API-INTEGRATION (kräver körande server) ───────────────────────────────


@pytest.mark.integration
class TestApiIntegration:
    """
    Kör med: pytest tests/test_admin_html.py -m integration -v
    Kräver körande server på localhost:8000 och ADMIN_KEY i env.
    """

    @pytest.fixture
    def base_url(self):
        return "http://localhost:8000"

    @pytest.fixture
    def headers(self):
        import os
        key = os.environ.get("ADMIN_KEY", "")
        return {"X-Admin-Key": key}

    def test_metrics_new_fields(self, base_url, headers):
        import httpx
        with httpx.Client() as client:
            resp = client.get(f"{base_url}/admin/metrics", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "recent_valuations" in data, f"Saknar recent_valuations. Fält: {list(data.keys())}"
            assert "valor_stats" in data, f"Saknar valor_stats. Fält: {list(data.keys())}"

    def test_assistant_stats_endpoint(self, base_url, headers):
        import httpx
        with httpx.Client() as client:
            resp = client.get(f"{base_url}/admin/assistant-stats", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "total_conversations" in data
            assert "phase_breakdown" in data
