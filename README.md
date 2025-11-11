# 🦘 AusCourseMiner
**Automated Web Scraper for Australian University Course Data**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Playwright](https://img.shields.io/badge/Playwright-Enabled-green)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup4-Used-yellow)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 📖 Overview
**AusCourseMiner** is a Python-based data engineering project that automates the extraction of course information from multiple **Australian university websites**.

It collects structured academic data such as:
- 🎓 **Course Title & Description**
- 🧾 **CRICOS Course Code**
- ⏱ **Total Course Duration**
- 💰 **Tuition Fee (Onshore & Offshore)**
- 🧍‍♂️ **Entry Requirements**
- 🔗 **Course URLs & Application Links**

The result is formatted as **SQL-ready data** for integration into databases or analytics pipelines.

---

## 🧩 Features
- Multi-site scraping with dynamic page rendering using **Playwright**
- HTML parsing via **BeautifulSoup4**
- String cleaning and normalization using **regex & pandas**
- Data export support:
  - `.xlsx`, `.csv`, `.sql`, `.json`
- Asynchronous scraping support with **asyncio**
- Modular and extendable scraping system

---

## ⚙️ Tech Stack
| Component | Library | Description |
|------------|----------|-------------|
| Headless Browser | `playwright` | For rendering and navigating dynamic content |
| HTML Parser | `beautifulsoup4` | For extracting course data from HTML |
| Data Cleaning | `re`, `pandas` | Regex-based and tabular cleaning |
| Async Runtime | `asyncio` | Concurrent scraping for performance |
| Data Export | `pandas`, `openpyxl` | To Excel, CSV, or SQL outputs |
| Database Integration | `mysql.connector` / `sqlite3` | For local storage or pipeline use |

---

## 🧰 Installation

```bash
# Clone the repository
git clone https://github.com/anakagung55/WebScraping-CourseCricos.git
cd WebScraping-CourseCricos

# Install dependencies
pip install -r requirements.txt
