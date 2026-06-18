import os
import json
import asyncio
from dotenv import load_dotenv
from simple_salesforce import Salesforce
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

def get_sf():
    return Salesforce(
        username=os.getenv("SF_USERNAME"),
        password=os.getenv("SF_PASSWORD"),
        consumer_key=os.getenv("SF_CLIENT_ID"),
        consumer_secret=os.getenv("SF_CLIENT_SECRET"),
        domain=os.getenv("SF_DOMAIN", "test")
    )

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
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "Id": {"type": "string", "description": "Account ID"},
            "Name": {"type": "string", "description": "Account Name"}
        }
    }
},
    {
        "name": "get_case_by_caseNumber",
        "description": "getCaseDetailsByCaseNumber",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_number": {"type": "string"}
            },
            "required": ["case_number"]
        }
    },
    {
        "name": "get_compliance_records",
        "description": "Fetch Compliance__c records",
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
    sf = get_sf()
    if name == "query_records":
        result = sf.query_all(args["soql"])
        return {"totalSize": result["totalSize"], "records": result["records"]}
    elif name == "get_compliance_records":
        query = "SELECT Id, Name, Store__c, Vendor__c, Status__c, Expiration_Date__c, Service_Start_Date__c FROM Compliance__c WHERE RecordType.Name = 'Pest_Control_Vendor'"
        if args.get("store_name"):
            query += f" AND Store__r.Name = '{args['store_name']}'"
        return sf.query_all(query)["records"]
    elif name == "get_case_by_caseNumber":
        query = f"SELECT Id, Subject, Description FROM Case WHERE CaseNumber = '{args['case_number']}'"
        return sf.query_all(query)["records"]
    elif name == "search_accounts":
        query = f"SELECT Id, Name FROM Account WHERE RecordType.DeveloperName = 'US_Store' AND Name LIKE '%{args['name_filter']}%' LIMIT 20"
        return sf.query_all(query)["records"]
    elif name == "create_compliance_record":
        result = sf.Compliance__c.create({
            "Store__c": args["store_id"],
            "Vendor__c": args["vendor"],
            "Expiration_Date__c": args["expiration_date"],
            "Service_Start_Date__c": args["service_start_date"],
            "Status__c": "Submitted"
        })
        return {"success": result["success"], "id": result["id"]}
    return {"error": "Unknown tool"}

async def health(request):
    return JSONResponse({"status": "ok", "server": "Salesforce MCP"})

async def mcp_handler(request):
    if request.method == "GET":
        async def event_stream():
            server_info = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {
                    "serverInfo": {"name": "Salesforce MCP Server", "version": "1.0.0"},
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

    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Salesforce MCP Server", "version": "1.0.0"},
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
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result)}]
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
