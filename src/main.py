"""DHCP Management API – FastAPI application entry point.

Run from the src/ directory:

    # HTTP (development / internal network)
    uvicorn main:app --host 0.0.0.0 --port 8080

    # HTTPS (recommended for production)
    # Generate a self-signed cert once:
    #   openssl req -x509 -newkey rsa:4096 -keyout C:\dhcp-api\key.pem -out C:\dhcp-api\cert.pem -days 3650 -nodes -subj "/CN=dhcp01.lab.local"
    # Then start with:
    #   uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-keyfile C:\dhcp-api\key.pem --ssl-certfile C:\dhcp-api\cert.pem
"""

import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI

from api.router import router
from core.security import require_api_key
from core.startup import validate_config

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),                                               # stderr (terminal / service manager)
        # logging.FileHandler(r"C:\dhcp-api\dhcp_api.log", encoding="utf-8"), # uncomment to also write to a file
    ],
)

validate_config()

app = FastAPI(
    title="Windows DHCP Management API",
    version="1.1.0",
    description="Provision and manage DHCP scopes on a Windows DHCP server via PowerShell.",
    dependencies=[Depends(require_api_key)],
)

app.include_router(router)
