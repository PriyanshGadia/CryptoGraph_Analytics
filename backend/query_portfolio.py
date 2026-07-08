import requests

def test_portfolio_endpoints():
    try:
        r = requests.get("http://localhost:8000/api/portfolio")
        print("Portfolio Status Code:", r.status_code)
        print("Portfolio Response:", r.json())
        
        r2 = requests.get("http://localhost:8000/api/portfolio/trades")
        print("Trades Status Code:", r2.status_code)
        print("Trades Total:", r2.json().get("total"))
    except Exception as e:
        print("Error connecting to backend API:", e)

if __name__ == "__main__":
    test_portfolio_endpoints()
