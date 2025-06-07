import requests
import json
from pprint import pprint
url = "https://BrsApi.ir/Api/Market/Gold_Currency.php?key=Free008FtJCiglltKcc57XI1ENJ2YxRz"

headers = {

    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/106.0.0.0",

    "Accept": "application/json, text/plain, */*"

}



# Send a GET request to the API
response = requests.get(url, headers=headers)

if response.status_code == 200:
    # Parse the JSON response
    data = json.loads(response.text)

    # Extract the price of the first gold item (18K Gold)
    gold_price = data['gold'][0]['price']

    print(gold_price * 10 )
else:
    print(f"Error: {response.status_code}")

