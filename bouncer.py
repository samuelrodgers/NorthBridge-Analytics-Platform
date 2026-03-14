from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

# Allow your landing page to talk to this bouncer
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://samrodgers.site", "https://www.samrodgers.site"],
    allow_methods=["GET"],
)

# --- CONFIG ---
SUPERSET_URL = "https://superset.samrodgers.site"
DASHBOARD_ID = "1e555cc9-9a7b-4a58-91d8-563eb178a77e" # Get this from Superset "Embed Dashboard" menu
ADMIN_USER = "superset_admin"
ADMIN_PASS = "1a14g2F1!"

@app.get("/get-token")
def get_token():
    # A. Get Admin Access Token
    auth = requests.post(f"{SUPERSET_URL}/api/v1/security/login", 
                         json={"username": ADMIN_USER, "password": ADMIN_PASS, "provider": "db"}).json()
    access_token = auth['access_token']

    # B. Fetch Guest Token for the dashboard
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "user": {"username": "guest_user", "first_name": "Samuel", "last_name": "Rodgers"},
        "resources": [{"type": "dashboard", "id": DASHBOARD_ID}],
        "rls": []
    }
    token_data = requests.post(f"{SUPERSET_URL}/api/v1/security/guest_token/", 
                               json=payload, headers=headers).json()
    return {"token": token_data['token']}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
