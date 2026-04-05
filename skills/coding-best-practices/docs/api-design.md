# API Design Guidelines

These rules prevent silent frontend failures where buttons appear to work but do nothing.

## 1. Always Add Route Names

```python
# CORRECT - route has a name for url_for()
@router.post("/api/search", name="clients_api_search")

# WRONG - no name, forces hardcoded URLs
@router.post("/api/search")
```

Route names enable:
- Centralized URL management
- Type-safe references in code
- Automatic updates when URLs change

---

## 2. Match HTTP Methods to Frontend Expectations

| Frontend Action | Backend Method | When to Use |
|----------------|----------------|-------------|
| Toggle/partial update | `PATCH` | Changing status, completing tasks |
| Full replacement | `PUT` | Replacing entire resource |
| Create new | `POST` | Creating resources |
| Fetch data | `GET` | Reading data |

### Common Bug

Frontend uses `PATCH` for partial updates (like task completion), but backend only has `PUT`. Add both if needed:

```python
@router.put("/api/{id}")      # Full update
@router.patch("/api/{id}")    # Partial update (status changes, toggles)
```

---

## 3. Match Content-Type Expectations

| Frontend Sends | Backend Parameter | Example |
|---------------|-------------------|---------|
| `JSON.stringify({...})` | Pydantic model | `task_data: TaskUpdateSchema` |
| `FormData` | `Form(...)` | `title: str = Form(...)` |

### Common Bug

Frontend sends JSON but backend expects Form data. Check the fetch call's `Content-Type` header.

```javascript
// Frontend sending JSON
fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'New Task' })
});
```

```python
# Backend must accept JSON body
@router.post("/api/tasks")
async def create_task(task_data: TaskCreateSchema):  # Pydantic model
    ...
```

---

## 4. Use Route Patterns in JavaScript

```javascript
// CORRECT - uses dynamic route pattern
window.location.href = buildUrl('clients_detail', {id: clientId});
fetch(window.ROUTE_PATTERNS.clients_api_search, {...});

// WRONG - hardcoded URL breaks if routes change
window.location.href = `/clients/${clientId}`;
fetch('/clients/api/search', {...});
```

### Setting Up Route Patterns

```python
# Python - expose routes to JavaScript
@app.get("/api/routes")
def get_routes():
    return {
        "clients_detail": "/clients/{id}",
        "clients_api_search": "/clients/api/search",
    }
```

```javascript
// JavaScript - build URLs from patterns
function buildUrl(routeName, params = {}) {
    let url = window.ROUTE_PATTERNS[routeName];
    for (const [key, value] of Object.entries(params)) {
        url = url.replace(`{${key}}`, value);
    }
    return url;
}
```

---

## 5. Route Name Conventions

- Use snake_case: `clients_detail`, `workflows_builder`
- Prefix with section: `auth_login`, `teams_detail`
- Suffix with action for CRUD: `clients_add`, `clients_edit`, `clients_delete`

```python
# Examples
@router.get("/", name="clients")
@router.get("/{id}", name="clients_detail")
@router.get("/add", name="clients_add")
@router.post("/", name="clients_create")
@router.put("/{id}", name="clients_update")
@router.delete("/{id}", name="clients_delete")
@router.post("/api/search", name="clients_api_search")
```

---

## 6. API Endpoint Integrity Testing

Create a test that catches mismatches:

```python
def test_api_endpoint_integrity():
    """Detect frontend/backend mismatches."""

    # 1. Collect all route names from backend
    backend_routes = {route.name: route for route in app.routes if route.name}

    # 2. Parse frontend JavaScript for fetch calls
    frontend_calls = extract_fetch_calls_from_js()

    # 3. Check each frontend call has matching backend route
    for call in frontend_calls:
        assert call.route_name in backend_routes, f"Dead endpoint: {call.route_name}"

        route = backend_routes[call.route_name]
        assert call.method in route.methods, f"Method mismatch: {call.route_name}"
```

This test suite detects:
- Dead endpoints (frontend calls non-existent routes)
- HTTP method mismatches (PATCH vs PUT)
- Content-Type mismatches (JSON vs Form)
- Missing route names

---

## 7. RESTful Resource Patterns

### Standard CRUD Endpoints

```python
# List resources
@router.get("/resources", name="resources_list")
async def list_resources(...) -> List[ResourceResponse]:

# Get single resource
@router.get("/resources/{id}", name="resources_detail")
async def get_resource(id: UUID, ...) -> ResourceResponse:

# Create resource
@router.post("/resources", name="resources_create", status_code=201)
async def create_resource(data: ResourceCreate, ...) -> ResourceResponse:

# Full update
@router.put("/resources/{id}", name="resources_update")
async def update_resource(id: UUID, data: ResourceUpdate, ...) -> ResourceResponse:

# Partial update
@router.patch("/resources/{id}", name="resources_patch")
async def patch_resource(id: UUID, data: ResourcePatch, ...) -> ResourceResponse:

# Delete resource
@router.delete("/resources/{id}", name="resources_delete", status_code=204)
async def delete_resource(id: UUID, ...):
```

### Nested Resources

```python
# Resources belonging to a parent
@router.get("/parents/{parent_id}/children", name="children_list")
@router.post("/parents/{parent_id}/children", name="children_create")

# Actions on resources
@router.post("/resources/{id}/archive", name="resources_archive")
@router.post("/resources/{id}/publish", name="resources_publish")
```

---

## 8. Error Response Consistency

Always return consistent error shapes:

```python
from fastapi import HTTPException

# Standard error format
class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
    field: Optional[str] = None

# Usage
raise HTTPException(
    status_code=400,
    detail="Email already registered"
)

# For validation errors, FastAPI returns:
# {"detail": [{"loc": ["body", "email"], "msg": "invalid email", "type": "value_error"}]}
```
