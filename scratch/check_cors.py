import requests

url = "https://cryptograph-analytics.onrender.com/api/v1/status"
headers = {
    "Origin": "https://crypto-graph-analytics.vercel.app",
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "content-type, x-api-key",
}

try:
    response = requests.options(url, headers=headers)
    print("OPTIONS status code:", response.status_code)
    print("OPTIONS headers:")
    for k, v in response.headers.items():
        print(f"  {k}: {v}")
except Exception as e:
    print("Error:", e)
