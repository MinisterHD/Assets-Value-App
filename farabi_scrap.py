import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import datetime
import schedule
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# Database configuration
DB_CONFIG = {
    'host': 'host.docker.internal',
    'database': 'assets_db',
    'user': 'postgres',
    'password': 'admin',
    'port': '5432'
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def create_database_schema():
    """Create the database tables with proper schema for time series data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create assets table
    create_assets_table = """
                          CREATE TABLE IF NOT EXISTS assets \
                          ( \
                              id \
                              SERIAL \
                              PRIMARY \
                              KEY, \
                              asset_name \
                              VARCHAR \
                          ( \
                              100 \
                          ) UNIQUE NOT NULL,
                              asset_name_en VARCHAR \
                          ( \
                              100 \
                          ),
                              asset_type VARCHAR \
                          ( \
                              50 \
                          ),
                              description TEXT,
                              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                              ); \
                          """

    # Create price history table
    create_price_history_table = """
                                 CREATE TABLE IF NOT EXISTS price_history \
                                 ( \
                                     id \
                                     SERIAL \
                                     PRIMARY \
                                     KEY, \
                                     asset_id \
                                     INTEGER \
                                     REFERENCES \
                                     assets \
                                 ( \
                                     id \
                                 ) ON DELETE CASCADE,
                                     price DECIMAL \
                                 ( \
                                     15, \
                                     2 \
                                 ) NOT NULL,
                                     recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                     source VARCHAR \
                                 ( \
                                     100 \
                                 )
                                     ); \
                                 """

    # Create index for faster queries
    create_indexes = """
                     CREATE INDEX IF NOT EXISTS idx_price_history_asset_id ON price_history(asset_id);
                     CREATE INDEX IF NOT EXISTS idx_price_history_recorded_at ON price_history(recorded_at);
                     CREATE INDEX IF NOT EXISTS idx_price_history_asset_time ON price_history(asset_id, recorded_at); \
                     """

    cursor.execute(create_assets_table)
    cursor.execute(create_price_history_table)
    cursor.execute(create_indexes)

    conn.commit()
    cursor.close()
    conn.close()


def get_or_create_asset(asset_name, asset_name_en=None, asset_type=None, description=None):
    """Get asset ID or create new asset if it doesn't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Try to get existing asset
    cursor.execute("SELECT id FROM assets WHERE asset_name = %s", (asset_name,))
    result = cursor.fetchone()

    if result:
        asset_id = result[0]
    else:
        # Create new asset
        insert_query = """
                       INSERT INTO assets (asset_name, asset_name_en, asset_type, description)
                       VALUES (%s, %s, %s, %s) RETURNING id \
                       """
        cursor.execute(insert_query, (asset_name, asset_name_en, asset_type, description))
        asset_id = cursor.fetchone()[0]
        conn.commit()
        logging.info(f"Created new asset: {asset_name}")

    cursor.close()
    conn.close()
    return asset_id


def add_price_record(asset_id, price, source=None):
    """Add a new price record to the price history"""
    conn = get_db_connection()
    cursor = conn.cursor()

    insert_query = """
                   INSERT INTO price_history (asset_id, price, recorded_at, source)
                   VALUES (%s, %s, %s, %s) \
                   """

    cursor.execute(insert_query, (asset_id, price, datetime.now(), source))
    conn.commit()
    cursor.close()
    conn.close()


def get_latest_price(asset_id):
    """Get the latest price for an asset"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
            SELECT price, recorded_at \
            FROM price_history
            WHERE asset_id = %s
            ORDER BY recorded_at DESC LIMIT 1 \
            """

    cursor.execute(query, (asset_id,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result


def scrape_with_requests():
    try:
        resp = requests.get(URL_Exir, headers=HEADERS)
        resp2 = requests.get(URL_Firouze, headers=HEADERS)
        resp3 = requests.get(URL_Gold, headers=HEADERS)
        resp4 = requests.get(URL_USD, headers=HEADERS)

        if resp.status_code != 200 or resp2.status_code != 200 or resp3.status_code != 200 or resp4.status_code != 200:
            logging.error(
                f"HTTP error: {resp.status_code}, {resp2.status_code}, {resp3.status_code}, {resp4.status_code}")
            return None

        # Parse Exir fund
        soup = BeautifulSoup(resp.text, "html.parser")
        price_elem = soup.find("span", {"class": "top-info_price-number__ZEf_q"})

        # Parse Firouze fund
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        price_elem2 = soup2.find("span", {"class": "top-info_price-number__ZEf_q"})

        # Parse Gold price
        soup3 = BeautifulSoup(resp3.text, "html.parser")
        gold_18_row = soup3.find("tr", {"data-market-nameslug": "geram18"})
        price_elem3 = None
        if gold_18_row:
            price_elem3 = gold_18_row.find("td", {"class": "nf"})

        # Parse USD price
        soup4 = BeautifulSoup(resp4.text, "html.parser")
        usd = soup4.find("tr", {"data-market-nameslug": "price_dollar_rl"})
        price_elem4 = None
        if usd:
            price_elem4 = usd.find("td", {"class": "nf"})

        if not price_elem or not price_elem2 or not price_elem3 or not price_elem4:
            logging.error("Could not find all price elements")
            return None

        # Extract and clean prices
        price_text = price_elem.get_text(strip=True).replace(",", "")
        price_text2 = price_elem2.get_text(strip=True).replace(",", "")
        price_text3 = price_elem3.get_text(strip=True).replace(",", "")
        price_text4 = price_elem4.get_text(strip=True).replace(",", "")

        # Convert to integers
        exir_price = int(price_text)
        firouze_price = int(price_text2)
        gold_price = int(price_text3)
        usd_price = int(price_text4)

        return (exir_price, firouze_price, gold_price, usd_price)

    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        return None


def scrape_and_store():
    """Scrape prices and store them in database with timestamp"""
    logging.info("Starting scraping process...")

    prices = scrape_with_requests()
    if prices:
        try:
            # Define assets with their metadata
            assets_info = [
                {
                    'name': 'اکسیر یکم',
                    'name_en': 'Exir First',
                    'type': 'Iranian Stock Exchange',
                    'description': 'صندوق سرمایه‌گذاری اکسیر یکم',
                    'price': prices[0],
                    'source': 'agah.com'
                },
                {
                    'name': 'فیروزه موفقیت',
                    'name_en': 'Firouze Success',
                    'type': 'Iranian Stock Exchange',
                    'description': 'صندوق سرمایه‌گذاری فیروزه موفقیت',
                    'price': prices[1],
                    'source': 'agah.com'
                },
                {
                    'name': 'طلا 18 عیار',
                    'name_en': 'Gold 18K',
                    'type': 'Commodity',
                    'description': 'طلای 18 عیار هر گرم',
                    'price': prices[2],
                    'source': 'tgju.org'
                },
                {
                    'name': 'دلار آمریکا',
                    'name_en': 'USD',
                    'type': 'Currency',
                    'description': 'دلار آمریکا',
                    'price': prices[3],
                    'source': 'tgju.org'
                }
            ]

            # Store each asset and its price
            for asset_info in assets_info:
                asset_id = get_or_create_asset(
                    asset_info['name'],
                    asset_info['name_en'],
                    asset_info['type'],
                    asset_info['description']
                )

                add_price_record(asset_id, asset_info['price'], asset_info['source'])

            logging.info(
                f"Successfully stored prices: Exir={prices[0]}, Firouze={prices[1]}, Gold={prices[2]}, USD={prices[3]}")

        except Exception as e:
            logging.error(f"Error updating database: {e}")
    else:
        logging.error("Failed to scrape prices")


def initialize_database():
    """Initialize the database and create tables"""
    try:
        create_database_schema()
        logging.info("Database schema initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")


if __name__ == "__main__":
    # Initialize database
    initialize_database()

    # Run initial scrape
    scrape_and_store()

    # Schedule scraping every 15 minutes
    schedule.every(15).minutes.do(scrape_and_store)

    logging.info("Scheduler started. Scraping every 15 minutes...")

    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)
