# Introduction to HTTP Requests and Responses

**Learning Objective:** Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.  
**Total Estimated Time:** 45 minutes  
**Target Audience:** Undergraduate Computer Science Students / Web Developers  

---

## 1. Hook & Protocol Foundations (3 mins)
The Hypertext Transfer Protocol (HTTP) is the foundational application-layer protocol powering the World Wide Web [W1]. Whenever a browser renders an application, fetches an API resource, or submits form data, an exchange of request and response messages occurs over TCP/IP (or QUIC in HTTP/3).

```
Client (Browser / Curl) -------- Request (Method + URI + Headers + Body) ------> Server
Client (Browser / Curl) <------- Response (Status Code + Headers + Body) -------- Server
```

---

## 2. Core Method: GET (8 mins)
According to RFC 9110 and MDN Web Docs [W1]:
- **Semantic Purpose:** The `GET` method requests transfer of a current selected representation for the target resource. In plain terms, it is used strictly to **retrieve** data without changing server state.
- **Characteristics:**
  - **Safe:** Executing a `GET` request does not alter the resource state on the origin server.
  - **Idempotent:** Making multiple identical `GET` requests produces the exact same server state as a single request.
  - **Parameters:** Carried within the URL query string (e.g., `/api/users?role=admin&limit=10`).
- **Common Nuance:** While HTTP specifications do not forbid a message body on `GET`, standard implementations and intermediaries may reject, discard, or ignore bodies on `GET` requests.

```http
GET /api/v1/courses/cs101 HTTP/1.1
Host: api.university.edu
Accept: application/json
```

---

## 3. Core Method: POST (8 mins)
- **Semantic Purpose:** The `POST` method requests that the target server process the representation enclosed in the request payload according to the resource's specific semantics. Common actions include creating a new database record, submitting an order, or appending to a log.
- **Characteristics:**
  - **Neither Safe nor Idempotent:** Repeating the same `POST` request multiple times will typically create multiple independent resources (e.g., duplicate orders or duplicate account entries).
  - **Data Transmission:** Payloads are transmitted inside the HTTP request body with appropriate `Content-Type` headers (e.g., `application/json`, `application/x-www-form-urlencoded`).
- **Security Reality:** `POST` is **not inherently more secure** than `GET` simply because parameters are in the body; transport encryption (HTTPS / TLS) is mandatory for securing both methods against eavesdropping.

```http
POST /api/v1/users HTTP/1.1
Host: api.university.edu
Content-Type: application/json
Content-Length: 52

{
  "username": "alex_dev",
  "email": "alex@example.org"
}
```

---

## 4. HTTP Status Code Taxonomies (9 mins)
HTTP status codes are 3-digit integers issued by a server in response to a client's request.

### 2xx Success: The action was successfully received, understood, and accepted
- `200 OK`: Standard response for successful requests with a payload.
- `201 Created`: The request succeeded and resulted in one or more new resources being created (standard for `POST`).
- `204 No Content`: The request succeeded, but the response payload is intentionally empty (common for `DELETE` or empty updates).

### 4xx Client Error: The client seems to have erred
- `400 Bad Request`: Server cannot process the request due to perceived client error (malformed JSON, invalid syntax).
- `401 Unauthorized`: Authentication is required and has failed or not been provided.
- `403 Forbidden`: Authenticated client does not have access rights to the content.
- `404 Not Found`: Server cannot find the requested resource URI.

### 5xx Server Error: The server failed to fulfill an apparently valid request
- `500 Internal Server Error`: Generic catch-all error indicating unexpected server-side exception.
- `502 Bad Gateway`: Server while acting as a gateway or proxy received an invalid response from an inbound upstream server.
- `503 Service Unavailable`: Server is currently not ready to handle the request (overloaded or down for maintenance).

---

## 5. Hands-on Activity: Terminal Inspection with cURL (8 mins)
Open your terminal and execute the following commands to inspect the HTTP exchange:

1. **Perform a GET request and inspect headers:**
   ```bash
   curl -i -X GET "https://httpbin.org/get?topic=http"
   ```
   *Observe the `HTTP/1.1 200 OK` status and query arguments echoed back.*

2. **Trigger a 404 Client Error:**
   ```bash
   curl -i "https://httpbin.org/status/404"
   ```
   *Notice the `404 NOT FOUND` code generated.*

3. **Perform a POST request with JSON payload:**
   ```bash
   curl -i -X POST "https://httpbin.org/post" \
        -H "Content-Type: application/json" \
        -d '{"student": "John Doe", "score": 95}'
   ```
   *Notice how the server confirms payload reception in the response.*

---

## 6. Supplementary Videos (4 mins)
- 🎥 **[HTTP Crash Course & Status Codes](https://www.youtube.com/watch?v=iYM2zFP3Zn0)** by Traversy Media  
  *Covers real request/response lifecycles, headers, and status code groups.*
- 🎥 **[REST API Concepts - GET vs POST Explained](https://www.youtube.com/watch?v=lsMQRaeKNDk)** by Web Dev Simplified  
  *Visual breakdown of idempotency and request body mechanics.*

---

## 7. Knowledge Check (3 mins)

1. **Which HTTP method is considered both safe and idempotent according to RFC 9110?**
   - A) POST
   - B) GET
   - C) PATCH
   - D) CONNECT
   *Answer:* **B**. `GET` retrieves data without mutating state on the server.

2. **A server accepts a POST request and creates a new user profile record. What is the most specific 2xx status code it should return?**
   - A) 200 OK
   - B) 204 No Content
   - C) 201 Created
   - D) 202 Accepted
   *Answer:* **C**. `201 Created` indicates the creation of a new resource.

3. **What is the fundamental difference between a 4xx and a 5xx status code?**
   - A) 4xx codes are network timeouts; 5xx codes are client browser errors.
   - B) 4xx codes denote client-side errors (bad syntax, missing auth, invalid URI); 5xx codes denote origin server failures.
   - C) 4xx codes only happen with GET; 5xx only with POST.
   - D) 5xx codes mean the client lacks permissions.
   *Answer:* **B**. 4xx points to client errors; 5xx indicates server-side faults.

---

## 8. Summary & Key Takeaways (2 mins)
- `GET` is safe and idempotent; intended for reading data.
- `POST` is not idempotent; intended for resource creation and non-idempotent operations. Neither is secure without HTTPS/TLS.
- `2xx` indicates success, `4xx` indicates client mistakes, and `5xx` represents upstream/internal server failures.

---

## References & Authority Citations
- **[W1] MDN Web Docs - HTTP Methods:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods
- **[W2] RFC 9110 - HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110.html
- **[B1] HTTP: The Definitive Guide** by David Gourley & Brian Totty (O'Reilly Media)

