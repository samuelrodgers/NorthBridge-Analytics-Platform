import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

SUPERSET_URL = "http://127.0.0.1:8088"
DASHBOARD_ID = "1e555cc9-9a7b-4a58-91d8-563eb178a77e"
ADMIN_USER = "superset_admin"
ADMIN_PASS = "1a14g2F1!"

@app.get("/get-token")
def get_token():
    try:
        # 1. Login
        login_url = f"{SUPERSET_URL}/api/v1/security/login"
        auth_payload = {"username": ADMIN_USER, "password": ADMIN_PASS, "provider": "db"}

        print(f"DEBUG: Attempting login to {login_url}")
        auth_resp = requests.post(login_url, json=auth_payload)

        # Check if the response is actually JSON
        if auth_resp.status_code != 200:
            return {"error": f"Login failed with status {auth_resp.status_code}", "raw": auth_resp.text}

        access_token = auth_resp.json().get('access_token')

        # 2. Get Guest Token
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "user": {"username": "guest", "first_name": "Guest", "last_name": "User"},
            "resources": [{"type": "dashboard", "id": DASHBOARD_ID}],
            "rls": []
        }

        r = requests.post(f"{SUPERSET_URL}/api/v1/security/guest_token/", json=payload, headers=headers)
        return r.json()

    except Exception as e:
        return {"error": "Bouncer Script Error", "details": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
