# DHCP Automation API

A FastAPI service that provisions and manages Windows DHCP scopes via PowerShell.
Runs directly on the Windows DHCP server and exposes a REST API for scope creation, DNS configuration, exclusion ranges, failover setup, and scope lifecycle management.

---

## Prerequisites

| Requirement          | Notes                                                                        |
| -------------------- | ---------------------------------------------------------------------------- |
| Windows Server       | With the **DHCP Server** role installed                                      |
| Python 3.10+         | [python.org](https://www.python.org/downloads/) — add to PATH during install |
| Run as Administrator | Or member of the **DHCP Administrators** local group                         |

---

## Installation

```powershell
# 1. Clone / copy the project to the server
cd C:\dhcp-api

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

> **PowerShell execution policy** – if `Activate.ps1` is blocked, run once:
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## Configuration

Edit [`src/core/config.py`](src/core/config.py) before first run:

```python
DEFAULT_DNS_SERVERS       = ["10.10.1.5", "10.10.1.6"]   # your DNS servers
DEFAULT_DNS_DOMAIN        = "lab.local"                    # your domain
DEFAULT_FAILOVER_PARTNER  = "dhcp02.lab.local"            # standby DHCP server
DEFAULT_LEASE_DURATION_DAYS = 8
```

---

## Authentication

Every request requires an `X-API-Key` header. The expected key is loaded from a `.env` file in the repo root.

**Create `.env` before first run:**

```
DHCP_API_KEY=your-secret-key
```

The server will refuse to start if `DHCP_API_KEY` is not set.

**Passing the key in requests:**

```powershell
curl -X POST http://dhcp01:8080/scopes `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-secret-key" `
  -d '{...}'
```

**Swagger UI (`/docs`):** click **Authorize** (top right), enter the key, click **Authorize** — all "Try it out" requests will include it automatically.

**GitHub Actions:** store the key as a repository secret and pass it as a header:

```yaml
-H "X-API-Key: ${{ secrets.DHCP_API_KEY }}"
```

---

## Running

```powershell
cd src

# HTTP (development / internal network)
uvicorn main:app --host 0.0.0.0 --port 8080

# HTTPS (recommended for production)
uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Interactive API docs are available at `http(s)://<server>:<port>/docs`.

---

## API Endpoints

| Method   | Path                            | Description                                               |
| -------- | ------------------------------- | --------------------------------------------------------- |
| `GET`    | `/health`                       | Check DHCP service reachability                           |
| `POST`   | `/scopes`                       | Create scope with DNS, exclusions, failover               |
| `GET`    | `/scopes`                       | List all scopes                                           |
| `GET`    | `/scopes/{scope_id}`            | Get scope details (info + options + exclusions)           |
| `GET`    | `/scopes/{scope_id}/exists`     | Check if a scope exists → `true`/`false`                  |
| `DELETE` | `/scopes/{scope_id}`            | Remove a scope (auto-removes failover relationship first) |
| `PATCH`  | `/scopes/{scope_id}/dns`        | Update DNS servers / domain suffix                        |
| `PATCH`  | `/scopes/{scope_id}/state`      | Activate or deactivate a scope                            |
| `POST`   | `/scopes/{scope_id}/exclusions` | Add exclusion range                                       |
| `DELETE` | `/scopes/{scope_id}/exclusions` | Remove exclusion range                                    |
| `GET`    | `/failover`                     | List failover relationships                               |

### Minimal create request

```json
{
  "scope_name": "VLAN-120-Engineering",
  "network": "10.20.120.0",
  "subnet_mask": "255.255.255.0",
  "start_range": "10.20.120.50",
  "end_range": "10.20.120.240",
  "gateway": "10.20.120.1",
  "failover": {}
}
```

DNS, exclusions, and failover defaults are applied from `config.py` when omitted.
Exclusion ranges must be within the scope's network (validated at request time).
See [`example_requests.json`](example_requests.json) for full examples.

### Update DNS for an existing scope

```
PATCH /scopes/10.20.120.0/dns
```

```json
{
  "dns_servers": ["10.10.1.5", "10.10.1.6"],
  "dns_domain": "corp.local"
}
```

`dns_domain` is optional — omit it to leave the current suffix unchanged.

### Activate / deactivate a scope

```
PATCH /scopes/10.20.120.0/state
```

```json
{ "state": "Inactive" }
```

Useful for temporarily disabling a cluster segment during maintenance without deleting it.

### Response codes

| Code  | Meaning                                                                                               |
| ----- | ----------------------------------------------------------------------------------------------------- |
| `200` | Request processed successfully                                                                        |
| `401` | Missing or invalid API key                                                                            |
| `201` | Scope created, all steps succeeded                                                                    |
| `207` | Scope created but a non-critical step failed (exclusions or failover) — inspect `steps[]`             |
| `404` | Scope or resource not found                                                                           |
| `409` | Conflict — scope already exists, or exclusion range has active leases                                 |
| `422` | Invalid request payload (bad IP, reversed range, out-of-network exclusion, invalid state value, etc.) |
| `500` | PowerShell command failed (scope was not created)                                                     |
| `503` | PowerShell unavailable, DHCP service unreachable, or access denied                                    |

---

## Project Structure

```
src/
├── main.py               # App entry point; calls validate_config() at startup
├── core/
│   ├── config.py         # Defaults (DNS, failover, exclusions, lease) — edit before first run
│   ├── startup.py        # Config validation — runs at startup, refuses to start on bad values
│   ├── security.py       # API key authentication dependency
│   └── decorators.py     # @log_route, @http_response
├── models/
│   ├── schemas.py        # Pydantic request/response models
│   └── validators.py     # Pure validation logic (no framework dependency)
├── services/
│   └── executor.py       # PowerShell runner, standalone service functions,
│                         #   DHCPProvisioner pipeline
└── api/
    ├── router.py
    └── routes/
        ├── health.py
        ├── scopes.py
        ├── exclusions.py
        ├── failover.py
        └── dns.py
tests/
├── helpers.py            # Shared CommandResult helpers (_ok, _fail, _unavailable)
├── test_validators.py    # Pure unit tests (no Windows needed)
├── test_schemas.py       # Pydantic validation tests (no Windows needed)
├── test_executor.py      # Service-layer tests with mocked PowerShell
└── test_routes.py        # HTTP-layer tests with mocked PowerShell
```

---

## Testing

Tests run on **any OS** — PowerShell is mocked.

```bash
# Activate venv first, then:
pytest

# Verbose output
pytest -v

# Single file
pytest tests/test_validators.py
```

---

## Logging

Logs are written to **stderr** (the terminal / process output). There is no log file by default.

Every request is logged with entry, outcome, and elapsed time:

```
2025-01-15 10:23:41 [INFO]  dhcp_api.routes.create_scope: → create_scope
2025-01-15 10:23:41 [INFO]  dhcp_api.executor: Executing: Add-DhcpServerv4Scope ...
2025-01-15 10:23:42 [INFO]  dhcp_api.routes.create_scope: ← create_scope OK (812 ms)
```

To also write logs to a file, uncomment the `FileHandler` line in `src/main.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),                                               # stderr — always on
        logging.FileHandler(r"C:\dhcp-api\dhcp_api.log", encoding="utf-8"),  # uncomment this line
    ],
)
```

Both handlers share the same format — logs go to stderr **and** the file simultaneously.
