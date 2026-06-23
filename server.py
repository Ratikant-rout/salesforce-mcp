import os
import json
import asyncio
import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

def get_sf_token():
    my_domain = os.getenv("SF_MY_DOMAIN_URL")
    url = f"{my_domain}/services/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("SF_CLIENT_ID"),
        "client_secret": os.getenv("SF_CLIENT_SECRET")
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    result = response.json()
    return result["access_token"], result["instance_url"]

def get_sf():
    print("[AUTH] Requesting access token via Client Credentials Flow...")
    try:
        access_token, instance_url = get_sf_token()
        print(f"[AUTH] Success! Instance: {instance_url}")
        sf = Salesforce(instance_url=instance_url, session_id=access_token)
        return sf
    except Exception as e:
        print(f"[AUTH ERROR] {str(e)}")
        raise

TOOLS = [
    {
        "name": "query_records",
        "description": "Run a SOQL query and return results",
        "inputSchema": {
            "type": "object",
            "properties": {
                "soql": {"type": "string"}
            },
            "required": ["soql"]
        }
    },
    {
        "name": "search_accounts",
        "description": "Search US Store accounts by name",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_filter": {"type": "string"}
            },
            "required": ["name_filter"]
        }
    },
    {
    "name": "get_case_by_caseNumber",
    "description": "Get case details by case number from Salesforce",
    "inputSchema": {
        "type": "object",
        "properties": {
            "case_number": {"type": "string"}
        },
        "required": ["case_number"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "Id": {"type": "string", "description": "Case record ID"},
            "CaseNumber": {"type": "string", "description": "Case number"},
            "Subject": {"type": "string", "description": "Case subject"},
            "Status": {"type": "string", "description": "Case status"},
            "Priority": {"type": "string", "description": "Case priority"},
            "Description": {"type": "string", "description": "Case description"}
        }
    }
},
    {
        "name": "get_compliance_records",
        "description": "Fetch Compliance__c records optionally filtered by store name",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_name": {"type": "string"}
            }
        }
    },
    {
        "name": "create_compliance_record",
        "description": "Create a new Compliance__c record",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "vendor": {"type": "string"},
                "expiration_date": {"type": "string"},
                "service_start_date": {"type": "string"}
            },
            "required": ["store_id", "vendor", "expiration_date", "service_start_date"]
        }
    }
]

def execute_tool(name, args):
    print(f"[TOOL] Executing: {name} | Args: {args}")

    try:
        sf = get_sf()
    except Exception as e:
        print(f"[TOOL ERROR] SF connection failed: {str(e)}")
        return {"error": f"Salesforce authentication failed: {str(e)}"}

    try:
        if name == "query_records":
            soql = args.get("soql", "")
            result = sf.query_all(soql)
            return {"totalSize": result["totalSize"], "records": result["records"]}

elif name == "get_case_by_caseNumber":
    case_number = args.get("case_number", "")
    query = f"""
        SELECT Id, CaseNumber, Subject, Description,
               Status, Priority, Origin, CreatedDate,
               Account.Name, Contact.Name
        FROM Case
        WHERE CaseNumber = '{case_number}'
    """
    result = sf.query_all(query)
    if result["totalSize"] == 0:
        return {"message": f"No case found with case number {case_number}"}
    return result["records"][0]  # ← return single object, not list

        elif name == "get_compliance_records":
            query = """
                SELECT Id, Name, Store__c, Vendor__c, Status__c,
                       Expiration_Date__c, Service_Start_Date__c
                FROM Compliance__c
                WHERE RecordType.Name = 'Pest_Control_Vendor'
            """
            if args.get("store_name"):
                query += f" AND Store__r.Name = '{args['store_name']}'"
            result = sf.query_all(query)
            return result["records"]

        elif name == "search_accounts":
            name_filter = args.get("name_filter", "")
            query = f"""
                SELECT Id, Name, Industry, Type, AnnualRevenue, NumberOfEmployees, RecordType.Name
                FROM Account
                WHERE Name LIKE '%{name_filter}%'
                LIMIT 20
            """
            result = sf.query_all(query)
            return result["records"]

        elif name == "create_compliance_record":
            payload = {
                "Store__c": args.get("store_id"),
                "Vendor__c": args.get("vendor"),
                "Expiration_Date__c": args.get("expiration_date"),
                "Service_Start_Date__c": args.get("service_start_date"),
                "Status__c": "Submitted"
            }
            result = sf.Compliance__c.create(payload)
            return {"success": result["success"], "id": result["id"]}

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        print(f"[TOOL ERROR] {name} failed: {str(e)}")
        return {"error": str(e)}

async def health(request):
    return JSONResponse({"status": "ok", "server": "Salesforce MCP"})

async def debug_auth(request):
    my_domain = os.getenv("SF_MY_DOMAIN_URL") or os.getenv("SF_MY_DOMAIN")
    client_id = os.getenv("SF_CLIENT_ID")
    client_secret = os.getenv("SF_CLIENT_SECRET")

    url = f"{my_domain}/services/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(url, data=data)
    return JSONResponse({
        "my_domain": my_domain,
        "client_id_length": len(client_id) if client_id else 0,
        "client_id_preview": f"{client_id[:15]}...{client_id[-10:]}" if client_id else None,
        "client_secret_length": len(client_secret) if client_secret else 0,
        "status": response.status_code,
        "response": response.text
    })

async def mcp_handler(request):
    if request.method == "GET":
        async def event_stream():
            server_info = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {
                    "serverInfo": {
                        "name": "Salesforce MCP Server",
                        "version": "1.0.0"
                    },
                    "capabilities": {"tools": {}}
                }
            }
            yield f"data: {json.dumps(server_info)}\n\n"
            await asyncio.sleep(30)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )

    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})

    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "Salesforce MCP Server",
                    "version": "1.0.0"
                },
                "capabilities": {"tools": {}}
            }
        })

    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })

elif method == "tools/call":
    tool_name = params.get("name")
    tool_args = params.get("arguments", {})
    try:
        result = execute_tool(tool_name, tool_args)
        
        # If result is a list (like case/account records), take first item for structured output
        structured_result = result
        if isinstance(result, list) and len(result) > 0:
            structured_result = result[0]
        elif isinstance(result, list) and len(result) == 0:
            structured_result = {"message": "No records found"}
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "structuredContent": structured_result
            }
        })
    except Exception as e:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": str(e)}
        })

    else:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

routes = [
    Route("/", health),
    Route("/debug-auth", debug_auth),
    Route("/mcp", mcp_handler, methods=["GET", "POST"]),
    Route("/sse", mcp_handler, methods=["GET", "POST"]),
]

app = Starlette(routes=routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
