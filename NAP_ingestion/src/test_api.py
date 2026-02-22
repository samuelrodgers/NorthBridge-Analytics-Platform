# test_api.py
import requests

response = requests.get('https://api.frankfurter.app/latest?from=EUR&to=USD,GBP,JPY')
print(response.json())