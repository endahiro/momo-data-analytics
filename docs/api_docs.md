# MoMo SMS Transactions API — Documentation

REST API for querying, creating, updating, and deleting MoMo mobile-money
transactions parsed from SMS backup XML.

- **Base URL:** `http://localhost:8000`
- **Content type:** all responses are `application/json; charset=utf-8`
- **Authentication:** HTTP Basic Auth on every endpoint

## Authentication

All endpoints require HTTP Basic Authentication. Send an
`Authorization: Basic <base64(username:password)>` header with every request.

Default demo credentials (set with `API_USERNAME` / `API_PASSWORD` env vars
to override):

| Field    | Value           |
|----------|-----------------|
| Username | `admin`         |
| Password | `password123`   |

Any request without a valid header receives `401 Unauthorized` and a
`WWW-Authenticate: Basic realm="MoMo API"` header prompting the client
to send credentials.

### Example — sending credentials with `curl`

```bash
curl -u admin:password123 http://localhost:8000/transactions
```

### Failure response — 401 Unauthorized

```
HTTP/1.0 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="MoMo API"

{"error": "Unauthorized"}
```

## Common error codes

| Status | Meaning                                                      |
|--------|--------------------------------------------------------------|
| `200`  | OK — request succeeded                                       |
| `201`  | Created — POST succeeded, new record returned in body        |
| `400`  | Bad Request — malformed JSON or missing required fields      |
| `401`  | Unauthorized — missing or invalid credentials                |
| `404`  | Not Found — transaction id doesn't exist / unknown route     |

---

## Endpoints

### 1. `GET /transactions`

List every transaction currently in memory.

**Request**

```bash
curl -u admin:password123 http://localhost:8000/transactions
```

**Response — 200 OK** (truncated; the array holds ~1,683 objects)

```json
[
  {
    "id": 1,
    "category": "Incoming Money",
    "amount": 2000.0,
    "fee": 0.0,
    "new_balance": 2000.0,
    "sender": "Jane Smith",
    "receiver": null,
    "counterparty_phone": "*********013",
    "tx_id": "76662021700",
    "external_tx_id": null,
    "tx_datetime": "2024-05-10 16:30:51",
    "sms_received_at": "2024-05-10T14:30:58.724000+00:00",
    "readable_date": "10 May 2024 4:30:58 PM",
    "raw_body": "You have received 2000 RWF from Jane Smith ..."
  }
]
```

**Errors:** `401` if unauthenticated.

---

### 2. `GET /transactions/{id}`

Fetch a single transaction by id.

**Request**

```bash
curl -u admin:password123 http://localhost:8000/transactions/1
```

**Response — 200 OK**

```json
{
  "id": 1,
  "category": "Incoming Money",
  "amount": 2000.0,
  "fee": 0.0,
  "sender": "Jane Smith",
  "tx_id": "76662021700"
}
```

**Response — 404 Not Found**

```json
{ "error": "Transaction 99999 not found" }
```

**Errors:** `401` if unauthenticated, `404` if id doesn't exist.

---

### 3. `POST /transactions`

Create a new transaction. The server assigns the id.

**Request body** — a JSON object. At minimum an `amount` field is required.
Any other fields you send are stored verbatim.

**Request**

```bash
curl -u admin:password123 -X POST http://localhost:8000/transactions \
     -H "Content-Type: application/json" \
     -d '{
           "category": "Bank Deposit",
           "amount": 5000,
           "receiver": "Account Owner"
         }'
```

**Response — 201 Created**

```json
{
  "id": 1692,
  "category": "Bank Deposit",
  "amount": 5000,
  "receiver": "Account Owner"
}
```

**Errors:**
- `400` if body is not valid JSON or is missing `amount`
- `401` if unauthenticated

---

### 4. `PUT /transactions/{id}`

Update an existing transaction. Fields in the body overwrite fields on the
existing record. Fields you don't send are left alone. The `id` cannot be
changed.

**Request**

```bash
curl -u admin:password123 -X PUT http://localhost:8000/transactions/1 \
     -H "Content-Type: application/json" \
     -d '{ "amount": 9999, "fee": 100 }'
```

**Response — 200 OK** (updated record)

```json
{
  "id": 1,
  "category": "Incoming Money",
  "amount": 9999,
  "fee": 100,
  "sender": "Jane Smith"
}
```

**Errors:**
- `400` if body is not valid JSON
- `401` if unauthenticated
- `404` if the id doesn't exist

---

### 5. `DELETE /transactions/{id}`

Remove a transaction.

**Request**

```bash
curl -u admin:password123 -X DELETE http://localhost:8000/transactions/3
```

**Response — 200 OK**

```json
{ "deleted": true, "id": 3 }
```

**Errors:**
- `401` if unauthenticated
- `404` if the id doesn't exist

---

## Health / discovery

### `GET /` and `GET /health`

Returns a short JSON description of the service so a plain browser visit
shows something useful.

```json
{
  "service": "MoMo SMS Transactions API",
  "status": "ok",
  "endpoints": [
    "GET    /transactions",
    "GET    /transactions/{id}",
    "POST   /transactions",
    "PUT    /transactions/{id}",
    "DELETE /transactions/{id}"
  ]
}
```

Still requires Basic Auth.

## A note on Basic Auth

Basic Auth is used here **because the assignment specifies it**, and because
it's a good teaching example. It's not a good production choice. See the
project's PDF report for a fuller discussion of why Basic Auth is weak
(credentials sent on every request, only obfuscated by Base64, no expiry,
no per-request signing, no revocation) and what a real deployment would use
instead (JWT bearer tokens, OAuth 2.0, or mutual TLS).
