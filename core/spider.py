import argparse
import asyncio
import json
import sys
from typing import List, Dict, Any, Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


class DVWASpider:
    """A small Playwright-based spider for DVWA-style apps.

    Features:
    - login to login.php using provided credentials
    - read and set security level on security.php
    - extract navigation targets from the left menu
    - for each discovered target page, extract anchor hrefs and form definitions
    - save structured results to a JSON file
    """

    def __init__(self, base_url: str, username: str = "admin", password: str = "password"):
        self.base_url = base_url.rstrip("/")
        self.auth = {"user": username, "pass": password}
        self.targets: List[Dict[str, Any]] = []
        self.results: Dict[str, Any] = {"base_url": self.base_url, "pages": []}

    async def login(self, page: Page) -> bool:
        try:
            await page.goto(f"{self.base_url}/login.php")
            # The DVWA login form uses name=username and name=password and an input with name=Login
            await page.fill('input[name="username"]', self.auth["user"])
            await page.fill('input[name="password"]', self.auth["pass"])
            await page.click('input[name="Login"]')
            # wait for navigation or some sign that login finished
            await page.wait_for_load_state("networkidle")
            print("[+] Login attempted")
            return True
        except Exception as e:
            print(f"[-] Login failed: {e}")
            return False

    async def get_security_level(self, page: Page) -> Optional[str]:
        try:
            await page.goto(f"{self.base_url}/security.php")
            # Read the selected option's value or text from the select[name="security"]
            sel = await page.query_selector('select[name="security"]')
            if not sel:
                return None
            selected = await sel.input_value()
            # input_value returns the value attribute of selected option
            return selected
        except Exception as e:
            print(f"[-] Could not read security level: {e}")
            return None

    async def set_security_level(self, page: Page, level: str) -> bool:
        try:
            await page.goto(f"{self.base_url}/security.php")
            # Try to set by option value. Common DVWA values: low, medium, high, impossible
            await page.select_option('select[name="security"]', level)
            await page.click('input[name="seclev_submit"]')
            await page.wait_for_load_state("networkidle")
            print(f"[+] Security Level Set To: {level}")
            return True
        except Exception as e:
            print(f"[-] Could not set security level: {e}")
            return False

    @staticmethod
    async def _extract_forms_from_page(page: Page) -> List[Dict[str, Any]]:
        forms_data: List[Dict[str, Any]] = []
        forms = await page.query_selector_all("form")
        for form in forms:
            try:
                action = await form.get_attribute("action") or ""
                method = (await form.get_attribute("method")) or "GET"
                inputs: List[Dict[str, Any]] = []

                # gather input fields, textareas and selects
                fields = await form.query_selector_all("input, textarea, select")
                for field in fields:
                    name = await field.get_attribute("name") or ""
                    ftype = await field.get_attribute("type") or ("textarea" if (await field.evaluate("el => el.tagName.toLowerCase()")) == "textarea" else "select")
                    value = await field.get_attribute("value") or ""
                    placeholder = await field.get_attribute("placeholder") or ""

                    field_data: Dict[str, Any] = {
                        "name": name,
                        "type": ftype,
                        "value": value,
                        "placeholder": placeholder,
                    }

                    # If select, gather options
                    tag_name = await field.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name == "select":
                        opts = []
                        options = await field.query_selector_all("option")
                        for opt in options:
                            opts.append({
                                "value": await opt.get_attribute("value"),
                                "text": await opt.inner_text(),
                                "selected": await opt.get_attribute("selected") is not None,
                            })
                        field_data["options"] = opts

                    inputs.append(field_data)

                forms_data.append({"action": action, "method": method.upper(), "inputs": inputs})
            except Exception as e:
                # Continue on form extraction errors
                print(f"[-] Error extracting a form: {e}")
                continue
        return forms_data

    @staticmethod
    async def _extract_anchors_from_page(page: Page, base_url: str) -> List[str]:
        anchors: List[str] = []
        a_elems = await page.query_selector_all("a")
        for a in a_elems:
            try:
                href = await a.get_attribute("href")
                if not href:
                    continue
                # Normalize relative URLs
                if href.startswith("/"):
                    full = f"{base_url}{href}"
                elif href.startswith("http://") or href.startswith("https://"):
                    full = href
                else:
                    # relative path
                    full = f"{base_url}/{href}".replace("//", "/").replace("http:/", "http://").replace("https:/", "https://")
                anchors.append(full)
            except Exception:
                continue
        # deduplicate while preserving order
        seen = set()
        uniq = []
        for u in anchors:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq

    async def crawl_targets(self, page: Page, nav_links: List[str], target_level: str):
        # Visit each discovered page and extract anchors and forms
        for url in nav_links:
            try:
                print(f"[+] Visiting {url}")
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                anchors = await self._extract_anchors_from_page(page, self.base_url)
                forms = await self._extract_forms_from_page(page)
                page_entry = {"url": url, "level": target_level, "anchors": anchors, "forms": forms}
                self.results["pages"].append(page_entry)
            except Exception as e:
                print(f"[-] Error crawling {url}: {e}")
                continue

    async def run(self, target_level: str = "low", headless: bool = True, output: str = "targets.json"):
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(headless=headless)
            context: BrowserContext = await browser.new_context()
            page: Page = await context.new_page()

            # 1. Login
            ok = await self.login(page)
            if not ok:
                print("[-] Aborting due to login failure")

            # 2. Security level
            current_level = await self.get_security_level(page)
            if current_level is None:
                print("[-] Could not detect current security level")
            else:
                print(f"[+] Current security level: {current_level}")

            # Attempt to set to the requested level if different
            if target_level and current_level != target_level:
                await self.set_security_level(page, target_level)

            # 3. Collect navigation links from left menu
            try:
                await page.goto(f"{self.base_url}/index.php")
                # 优化点 1：等待菜单容器出现，增加成功率
                await page.wait_for_selector('#main_menu', timeout=5000)

                # 优化点 2：使用更宽泛的选择器，抓取 id 包含 menu 的 div 下的所有链接
                nav_links_elems = await page.query_selector_all('div[id*="menu"] a')

                nav_hrefs: List[str] = []
                for a in nav_links_elems:
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("http://") or href.startswith("https://"):
                        full = href
                    else:
                        full = f"{self.base_url}/{href.lstrip('./')}"
                    nav_hrefs.append(full)

                # dedupe
                seen = set()
                nav_hrefs_clean: List[str] = []
                for n in nav_hrefs:
                    if n not in seen:
                        seen.add(n)
                        nav_hrefs_clean.append(n)

                print(f"[+] Found {len(nav_hrefs_clean)} nav links")

                # 4. Crawl each page and extract anchors and forms
                await self.crawl_targets(page, nav_hrefs_clean, target_level)

            except Exception as e:
                print(f"[-] Error while collecting nav links: {e}")

            # 5. Save results
            with open(output, "w", encoding="utf-8") as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"[+] Results written to {output}")

            await browser.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="DVWA spider using Playwright")
    parser.add_argument("--base", "-b", default="http://127.0.0.1/dvwa", help="Base URL of the target DVWA instance")
    parser.add_argument("--user", "-u", default="admin", help="Username")
    parser.add_argument("--pass", "-p", dest="password", default="password", help="Password")
    parser.add_argument("--level", "-l", default="low", help="Target security level (low|medium|high|impossible)")
    parser.add_argument("--output", "-o", default="targets.json", help="Output JSON file")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run browser visible for debugging")

    args = parser.parse_args(argv)

    spider = DVWASpider(args.base, args.user, args.password)
    try:
        asyncio.run(spider.run(target_level=args.level, headless=args.headless, output=args.output))
    except KeyboardInterrupt:
        print("[!] Interrupted by user")
        return 1
    except Exception as e:
        print(f"[!] Unhandled error: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

