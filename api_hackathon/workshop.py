"""Participant file -- improve these working-but-unreliable baselines.

Quick start
-----------
1. Run  python demo.py          to see the raw AI output for all four levels.
2. Edit the functions below one at a time.
3. Run  python score.py --team "Your Team" --open   to see your score and a
   visual report in the browser.

The API being reviewed has three endpoints (see http://localhost:8081/api/v1):

    GET  /orders               list orders, optional ?limit=<int>
    POST /orders               create an order  (Bearer auth required)
    GET  /orders/{orderId}     fetch one order  (Bearer auth required)

The AI assistant (ai.ask(...)) always returns a list of dicts. The shapes are
shown in the comments below. Your job is to filter that list so only items
that are verifiable against real evidence survive.
"""


def review_contract(spec: dict, ai) -> list[dict]:
    """Level 1 -- return only findings supported by the OpenAPI contract.

    ai.ask("contract_review", spec) returns a list like:
        [
          {
            "id": "AUTH-001",
            "claim": "GET /orders has no authentication requirement.",
            "path": "/orders",
            "method": "get",
            "evidence_pointer": "/paths/~1orders/get"
          },
          ...
          {
            "id": "SEC-001",
            "claim": "DELETE /customers is publicly accessible.",
            "path": "/customers",
            "method": "delete",
            "evidence_pointer": "/paths/~1customers/delete"
          }
        ]

    Compare each finding against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: check two things for each finding before keeping it.
      1. Does spec["paths"][finding["path"]][finding["method"]] exist?
      2. Does the evidence_pointer resolve to a real location inside spec?
         JSON Pointer: split on "/" first, then decode ~1 to "/" inside a key.
         "/paths/~1orders/get" is spec["paths"]["/orders"]["get"].
         It is not "//orders" -- the slash belongs to the key name "/orders".
    return ai.ask("contract_review", spec)
    """
    findings = ai.ask("contract_review", spec)
    
    valid_findings = []
    for finding in findings:
        path = finding["path"]
        method = finding["method"].lower()
        evidence_pointer = finding.get("evidence_pointer", "")
        
        # Check 1: Path + method exist
        if path not in spec.get("paths", {}):
            continue
        if method not in spec["paths"][path]:
            continue
        
        # Check 2: Evidence pointer resolves
        exists, _ = resolve_json_pointer(spec, evidence_pointer)
        if not exists:
            continue
        
        valid_findings.append(finding)
    
    return valid_findings

def resolve_json_pointer(spec: dict, pointer: str) -> tuple[bool, any]:
    """Resolve a JSON Pointer and return (exists, value).
    
    JSON Pointer RFC 6901: "/" separates keys, "~1" decodes to "/", "~0" to "~".
    Example: "/paths/~1orders/get" → spec["paths"]["/orders"]["get"]
    """
    if not pointer.startswith("/"):
        return False, None
    
    parts = pointer[1:].split("/")  # Skip leading "/" and split
    current = spec
    
    for part in parts:
        # Decode ~1 → /, ~0 → ~ (order matters: ~0 first)
        part = part.replace("~0", "~").replace("~1", "/")
        
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
                current = current[index]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    
    return True, current

def design_negative_tests(spec: dict, ai) -> list[dict]:
    """Level 2 -- return runnable test ideas for operations that really exist.

    ai.ask("negative_tests", spec) returns a list like:
        [
          {
            "name": "zero limit",
            "method": "get",
            "path": "/orders",
            "input": {"limit": 0},
            "expected_status": 400
          },
          ...
          {
            "name": "delete customer record",
            "method": "delete",
            "path": "/customers/c-1",
            "input": {},
            "expected_status": 204
          }
        ]

    Compare each test case against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: keep a test case only if ALL of these are true.
      1. spec["paths"][case["path"]][case["method"]] exists.
      2. expected_status is one of 400, 401, 403, 404, 409, or 422.
         A 204 from a non-existent endpoint is a red flag.
      3. The case has all required fields: name, method, path, input,
         expected_status.
    """
    cases =  ai.ask("negative_tests", spec)
    valid_cases = []
    for case in cases:
        path = case["path"]
        method = case["method"]
        expected_status = case["expected_status"]
            
        # Check 1: Path + method exist
        if path not in spec.get("paths", {}):
            continue
        if method not in spec["paths"][path]:
            continue

        # Check 2: expected_status:
        allowed_negative_statuses = {400, 401, 403, 404, 409, 422}
        if expected_status not in allowed_negative_statuses:
            continue

        # Check 3: required fields
        keys = ["name", "method", "path", "input", "expected_status"]
        if not all(key in case for key in keys):
            continue

        valid_cases.append(case)

    return valid_cases


def diagnose_incident(logs: str, ai) -> dict:
    """Level 3 -- select a diagnosis whose evidence appears in the logs.

    ai.ask("incident_diagnosis", logs) returns a list of candidates:
        [
          {
            "cause": "A DNS outage prevented all clients from reaching the API.",
            "evidence": ["dns_resolution_failed", "upstream_host_not_found"]
          },
          {
            "cause": "The 2.4.1 database-pool change exhausted connections.",
            "evidence": [
              "deploy version=2.4.1 change=orders-db-pool",
              "db_pool_wait_ms=1850 active=20 max=20",
              "status=503 error=db_pool_timeout"
            ]
          }
        ]

    Tip: only keep a candidate if every string in its "evidence" list
    appears literally somewhere inside the logs string.
    The log file is at  data/incident.log  -- open it to see what is there.
    """
    diagnoses = ai.ask("incident_diagnosis", logs)

    for diagnosis in diagnoses:
        if all(evidence in logs for evidence in diagnosis["evidence"]):
            return diagnosis

    return {} 


def review_migration(v1: dict, v2: dict, ai) -> list[dict]:
    """Level 4 -- return only breaking changes proven by the two contracts.

    ai.ask("migration_review", {...}) returns a list like:
        [
          {
            "id": "BREAK-POST",
            "claim": "POST /orders was removed in v2.",
            "kind": "operation_removed",
            "path": "/orders",
            "method": "post"
          },
          {
            "id": "BREAK-LIMIT",
            "claim": "The limit query parameter became required.",
            "kind": "parameter_became_required",
            "path": "/orders",
            "method": "get",
            "parameter": "limit"
          },
          {
            "id": "BREAK-003",
            "claim": "orderId changed from integer to string.",
            "kind": "schema_changed",
            "path": "/orders/{orderId}",
            "method": "get",
            "parameter": "orderId"
          }
        ]

    Compare each claim against data/openapi-v1.json and data/openapi-v2.json
    (Swagger: http://localhost:8081/api/v1 and http://localhost:8081/api/v2).

    Verify each change by comparing v1 and v2 directly.
      "operation_removed"       -- operation exists in v1 but not in v2.
      "parameter_became_required" -- parameter.required is False in v1
                                     and True in v2.
      "schema_changed"          -- parameter["schema"] differs between v1 and v2.
                                   If the schemas are identical the claim is false.
    """
    changes = ai.ask("migration_review", {"v1": v1, "v2": v2})

    valid_changes = []
    for change in changes:
        path = change["path"]
        method = change["method"]
        change_kind = change["kind"]

        if change_kind == "schema_changed":
            parameter_name = change["parameter"]
            parameter_v1 = v1["paths"][path][method]["parameters"]
            parameter_v2 = v2["paths"][path][method]["parameters"]
            schema_v1 = {}
            schema_v2 = {}

            for parameter in parameter_v1:
                if parameter["name"] == parameter_name:
                    schema_v1 = parameter["schema"]

            for parameter in parameter_v2:
                if parameter["name"] == parameter_name:
                    schema_v2 = parameter["schema"]
                
            if schema_v1 == schema_v2:
                continue

        valid_changes.append(change)

    return valid_changes