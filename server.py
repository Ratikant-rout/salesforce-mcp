import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from simple_salesforce import Salesforce
import uvicorn

load_dotenv()

mcp = FastMCP("Salesforce MCP Server")

def get_sf():
    return Salesforce(
        username=os.getenv("SF_USERNAME"),
        password=os.getenv("SF_PASSWORD"),
        consumer_key=os.getenv("SF_CLIENT_ID"),
        consumer_secret=os.getenv("SF_CLIENT_SECRET"),
        domain=os.getenv("SF_DOMAIN", "test")
    )

@mcp.tool()
def query_records(soql: str) -> dict:
    """Run a SOQL query and return results."""
    sf = get_sf()
    result = sf.query_all(soql)
    return {"totalSize": result["totalSize"], "records": result["records"]}

@mcp.tool()
def get_compliance_records(store_name: str = None) -> dict:
    """Fetch Compliance__c records filtered by store name."""
    sf = get_sf()
    query = """
        SELECT Id, Name, Store__c, Vendor__c, Status__c,
               Expiration_Date__c, Service_Start_Date__c
        FROM Compliance__c
        WHERE RecordType.Name = 'Pest_Control_Vendor'
    """
    if store_name:
        query += f" AND Store__r.Name = '{store_name}'"
    result = sf.query_all(query)
    return result["records"]

@mcp.tool()
def search_accounts(name_filter: str) -> list:
    """Search US Store accounts by name."""
    sf = get_sf()
    query = f"""
        SELECT Id, Name
        FROM Account
        WHERE RecordType.DeveloperName = 'US_Store'
        AND Name LIKE '%{name_filter}%'
        LIMIT 20
    """
    result = sf.query_all(query)
    return result["records"]

@mcp.tool()
def create_compliance_record(
    store_id: str,
    vendor: str,
    expiration_date: str,
    service_start_date: str
) -> dict:
    """Create a new Compliance__c record."""
    sf = get_sf()
    result = sf.Compliance__c.create({
        "Store__c": store_id,
        "Vendor__c": vendor,
        "Expiration_Date__c": expiration_date,
        "Service_Start_Date__c": service_start_date,
        "Status__c": "Submitted"
    })
    return {"success": result["success"], "id": result["id"]}

@mcp.tool()
def update_record_status(record_id: str, status: str) -> dict:
    """Update Status__c on a Compliance__c record."""
    sf = get_sf()
    sf.Compliance__c.update(record_id, {"Status__c": status})
    return {"updated": record_id, "status": status}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(
        app=mcp.sse_app(),
        host="0.0.0.0",
        port=port
    )