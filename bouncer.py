import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
SUPERSET_URL = "http://127.0.0.1:8088"
ALLOWED_DASHBOARDS = [
    "4f55a708-c316-406e-8480-1aa3d071631f",
    "813326be-8203-4dce-9908-25e28d9f0e6e",
    "0b663ea7-b0d8-4611-9ca4-a8761e17d875",
    "75c09c9f-faf0-448b-9215-bda18bbf87f7"
]
ADMIN_USER = "superset_admin"
ADMIN_PASS = "1a14g2F1!"
@app.get("/get-token")
def get_token(dashboard_id: str = Query(..., description="UUID of the dashboard to embed")):
    if dashboard_id not in ALLOWED_DASHBOARDS:
        raise HTTPException(status_code=403, detail="Dashboard not authorized")
    try:
        login_url = f"{SUPERSET_URL}/api/v1/security/login"
        auth_payload = {"username": ADMIN_USER, "password": ADMIN_PASS, "provider": "db"}
        auth_resp = requests.post(login_url, json=auth_payload)
        if auth_resp.status_code != 200:
            return {"error": f"Login failed with status {auth_resp.status_code}"}
        access_token = auth_resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "user": {"username": "guest", "first_name": "Guest", "last_name": "User"},
            "resources": [{"type": "dashboard", "id": dashboard_id}],
            "rls": []
        }
        r = requests.post(
            f"{SUPERSET_URL}/api/v1/security/guest_token/",
            json=payload,
            headers=headers
        )
        return r.json()
    except Exception as e:
        return {"error": "Bouncer Script Error", "details": str(e)}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
