import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 "
                   "(Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/95.0.4638.69 Safari/537.36"
}

URL_Exir = "https://research.agah.com/fund/mutual/14004329930"
URL_Firouze = "https://research.agah.com/fund/mutual/10320814789"
URL_Gold = "https://www.tgju.org/"
URL_USD = "https://www.tgju.org/%D9%82%DB%8C%D9%85%D8%AA-%D8%AF%D9%84%D8%A7%D8%B1"

def scrape_with_requests():
    resp = requests.get(URL_Exir, headers=HEADERS)
    resp2 = requests.get(URL_Firouze, headers=HEADERS)
    resp3 = requests.get(URL_Gold, headers=HEADERS)
    resp4 = requests.get(URL_USD, headers=HEADERS)
    if resp.status_code != 200 or resp2.status_code != 200 or resp3.status_code != 200 or resp4.status_code != 200:
        print(f"→ HTTP {resp.status_code , resp2.status_code , resp3.status_code , resp4.status_code} error")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    price_elem = soup.find("span", { "class": "top-info_price-number__ZEf_q" })
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    price_elem2 = soup2.find("span", {"class": "top-info_price-number__ZEf_q"})

    soup3 = BeautifulSoup(resp3.text, "html.parser")
    gold_18_row = soup3.find("tr", {"data-market-nameslug": "geram18"})
    if gold_18_row:
        price_elem3 = gold_18_row.find("td", {"class": "nf"})

    soup4 = BeautifulSoup(resp4.text, "html.parser")
    usd = soup4.find("tr", {"data-market-nameslug": "price_dollar_rl"})
    if usd:
        price_elem4 = usd.find("td", {"class": "nf"})


    if not price_elem or not price_elem2 or not price_elem3 or not price_elem4:
        return None

    price_text = price_elem.get_text(strip=True)
    price_text2 = price_elem2.get_text(strip=True)
    price_text3 = price_elem3.get_text(strip=True)
    price_text4 = price_elem4.get_text(strip=True)
    price_text = price_text.replace(",", "")
    price_text2 = price_text2.replace(",", "")
    price_text3 = price_text3.replace(",", "")
    price_text4 = price_text4.replace(",", "")
    price_text = int(price_text)
    price_text2 = int(price_text2)
    price_text3 = int(price_text3)
    price_text4 = int(price_text4)
    return (price_text,price_text2,price_text3,price_text4)

if __name__ == "__main__":
    p = scrape_with_requests()
    if p:
        print(f"اکسیر یکم {p[0]} ")
        print(f"فیروزه موفقیت {p[1]} ")
        print(f"طلا {p[2]} ")
        print(f"دلار {p[3]} ")

