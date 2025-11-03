import asyncio
from playwright.async_api import async_playwright

async def test_federation_one():
    url = "https://www.federation.edu.au/courses/den8.civ-bachelor-of-engineering-civil-honours"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # ubah ke True kalau tanpa GUI
        page = await browser.new_page()
        print(f"🌐 Opening {url}")
        await page.goto(url, timeout=90000)

        # === Klik tab "International" ===
        await page.wait_for_selector("button:has-text('International')", timeout=30000)
        await page.click("button:has-text('International')")
        await page.wait_for_timeout(4000)

        # === Scroll sedikit ke bawah ===
        await page.mouse.wheel(0, 5000)
        await page.wait_for_timeout(2000)

        # === Klik accordion "How to apply" ===
        try:
            await page.click("button:has-text('How to apply')")
            await page.wait_for_timeout(3000)
        except Exception:
            print("⚠️ Gagal klik 'How to apply' (mungkin sudah terbuka)")

        # === Tunggu elemen <dl> muncul ===
        await page.wait_for_selector("dl", timeout=20000)

        # === Ambil CRICOS code via evaluate ===
        cricos_code = await page.evaluate("""
            () => {
                const dts = Array.from(document.querySelectorAll('dt'));
                for (const dt of dts) {
                    if (dt.textContent.toLowerCase().includes('cricos')) {
                        const dd = dt.nextElementSibling;
                        return dd ? dd.textContent.trim() : '';
                    }
                }
                return '';
            }
        """)

        if cricos_code:
            print(f"✅ CRICOS ditemukan: {cricos_code}")
        else:
            print("❌ CRICOS tidak ditemukan.")

        await browser.close()

asyncio.run(test_federation_one())
