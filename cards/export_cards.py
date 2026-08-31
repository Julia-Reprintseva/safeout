"""Export each SafeOut social card as a PNG at 2x resolution."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML_FILE = Path(__file__).parent / "index.html"
OUT_DIR = Path(__file__).parent / "png"
OUT_DIR.mkdir(exist_ok=True)

# card selector, output filename, real dimensions (px at 1x)
CARDS = [
    (".c01", "01-intro-square-1080x1080.png",       400, 400),
    (".c02", "02-how-it-works-1080x1080.png",        400, 400),
    (".c03", "03-sos-1080x1080.png",                 400, 400),
    (".c07", "04-timeline-1080x1080.png",             400, 400),
    (".c04", "05-chat-story-1080x1920.png",           270, 480),
    (".c05", "06-for-contact-story-1080x1920.png",    270, 480),
    (".c06", "07-linkedin-1200x628.png",              560, 293),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(device_scale_factor=2.7)

    page.goto(f"file://{HTML_FILE}")
    page.wait_for_load_state("networkidle")

    for selector, filename, w, h in CARDS:
        el = page.query_selector(selector)
        if not el:
            print(f"SKIP {selector} — not found")
            continue
        out = OUT_DIR / filename
        el.screenshot(path=str(out))
        print(f"✓  {filename}")

    browser.close()

print(f"\nDone — files in {OUT_DIR}")
