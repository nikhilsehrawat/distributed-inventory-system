from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, json, uuid

ROOT = Path(__file__).parent
DB = ROOT / "data" / "inventory.db"
app = FastAPI(title="Distributed Inventory Processing System", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

def now():
    return datetime.now(timezone.utc).isoformat()

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, location TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT DEFAULT 'General', reorder_level INTEGER NOT NULL DEFAULT 10);
        CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), warehouse_id INTEGER NOT NULL REFERENCES warehouses(id), quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0), updated_at TEXT NOT NULL, UNIQUE(product_id, warehouse_id));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event_id TEXT UNIQUE, event_type TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, severity TEXT NOT NULL, message TEXT NOT NULL, resolved INTEGER DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS marketplace_stock(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), marketplace TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, UNIQUE(product_id, marketplace));
        """)
        if c.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0:
            c.executemany("INSERT INTO warehouses(name,location) VALUES(?,?)", [
                ("Gwalior Central Warehouse","Gwalior, MP"),("Delhi Distribution Hub","Delhi, India"),("Mumbai Fulfilment Hub","Mumbai, MH")])
            c.executemany("INSERT INTO suppliers(name,email) VALUES(?,?)", [
                ("North Star Textiles","supply@northstar.example"),("Urban Fabrics Co.","orders@urbanfabrics.example")])
            c.executemany("INSERT INTO products(sku,name,category,reorder_level) VALUES(?,?,?,?)", [
                ("GRD-TS-001","Essential Cotton T-Shirt","Apparel",15),("GRD-HD-002","Classic Hoodie","Apparel",10),("GRD-JN-003","Relaxed Denim Jeans","Denim",8),("GRD-CP-004","Everyday Cap","Accessories",12)])
            rows = c.execute("SELECT id FROM products").fetchall()
            whs = c.execute("SELECT id FROM warehouses").fetchall()
            quantities = [[42,28,16],[8,22,12],[17,9,24],[6,19,14]]
            for pi,p in enumerate(rows):
                for wi,w in enumerate(whs):
                    q = quantities[pi][wi]
                    c.execute("INSERT INTO inventory(product_id,warehouse_id,quantity,updated_at) VALUES(?,?,?,?)",(p["id"],w["id"],q,now()))
            for p in rows:
                c.execute("INSERT INTO marketplace_stock(product_id,marketplace,quantity,updated_at) VALUES(?,?,?,?)",(p["id"],"GRIDOH Store",20,now()))
            c.execute("INSERT INTO events(event_id,event_type,source,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()),"SYSTEM_INITIALIZED","seed",json.dumps({"message":"Demo data created"}),"processed",now()))
        c.commit()

init_db()

class WarehouseIn(BaseModel):
    name: str
    location: str
class SupplierIn(BaseModel):
    name: str
    email: str = ""
class ProductIn(BaseModel):
    sku: str
    name: str
    category: str = "General"
    reorder_level: int = Field(default=10, ge=0)
class StockIn(BaseModel):
    product_id: int
    warehouse_id: int
    quantity: int = Field(ge=0)
    source: str = "manual"
    reason: str = "Stock adjustment"
class MarketplaceIn(BaseModel):
    product_id: int
    marketplace: str
    quantity: int = Field(ge=0)

def record_event(c, event_type, source, payload, status="processed"):
    c.execute("INSERT INTO events(event_id,event_type,source,payload,status,created_at) VALUES(?,?,?,?,?,?)",
              (str(uuid.uuid4()),event_type,source,json.dumps(payload),status,now()))

def check_alert(c, product_id, warehouse_id, qty):
    p = c.execute("SELECT name,reorder_level FROM products WHERE id=?",(product_id,)).fetchone()
    w = c.execute("SELECT name FROM warehouses WHERE id=?",(warehouse_id,)).fetchone()
    if p and w and qty <= p["reorder_level"]:
        msg = f"Low stock: {p['name']} has {qty} units at {w['name']} (reorder level: {p['reorder_level']})."
        exists = c.execute("SELECT id FROM alerts WHERE message=? AND resolved=0",(msg,)).fetchone()
        if not exists:
            c.execute("INSERT INTO alerts(severity,message,created_at) VALUES(?,?,?)",("warning",msg,now()))

@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status":"healthy","service":"inventory-api","database":"SQLite demo store","timestamp":now()}

@app.get("/api/dashboard")
def dashboard():
    with conn() as c:
        products = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        warehouses = c.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0]
        units = c.execute("SELECT COALESCE(SUM(quantity),0) FROM inventory").fetchone()[0]
        low = c.execute("""SELECT COUNT(*) FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.quantity<=p.reorder_level""").fetchone()[0]
        alerts = c.execute("SELECT COUNT(*) FROM alerts WHERE resolved=0").fetchone()[0]
        events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"products":products,"warehouses":warehouses,"total_units":units,"low_stock_rows":low,"open_alerts":alerts,"processed_events":events}

@app.get("/api/inventory")
def inventory():
    with conn() as c:
        rows = c.execute("""SELECT p.id product_id,p.sku,p.name product,p.category,p.reorder_level,
            w.id warehouse_id,w.name warehouse,i.quantity,i.updated_at,
            CASE WHEN i.quantity<=p.reorder_level THEN 'LOW' ELSE 'HEALTHY' END status
            FROM inventory i JOIN products p ON p.id=i.product_id JOIN warehouses w ON w.id=i.warehouse_id
            ORDER BY p.name,w.name""").fetchall()
        return [dict(r) for r in rows]

@app.post("/api/stock")
def update_stock(data: StockIn):
    with conn() as c:
        exists = c.execute("SELECT quantity FROM inventory WHERE product_id=? AND warehouse_id=?",(data.product_id,data.warehouse_id)).fetchone()
        if not exists: raise HTTPException(404,"Product/warehouse inventory record not found")
        old = exists["quantity"]
        c.execute("UPDATE inventory SET quantity=?,updated_at=? WHERE product_id=? AND warehouse_id=?",
                  (data.quantity,now(),data.product_id,data.warehouse_id))
        payload = {"product_id":data.product_id,"warehouse_id":data.warehouse_id,"old_quantity":old,"new_quantity":data.quantity,"reason":data.reason}
        record_event(c,"STOCK_UPDATED",data.source,payload)
        check_alert(c,data.product_id,data.warehouse_id,data.quantity)
        c.commit()
        return {"success":True,"previous_quantity":old,"new_quantity":data.quantity,"event":"STOCK_UPDATED"}

@app.get("/api/warehouses")
def warehouses():
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM warehouses ORDER BY id").fetchall()]

@app.post("/api/warehouses")
def add_warehouse(data: WarehouseIn):
    with conn() as c:
        try:
            cur=c.execute("INSERT INTO warehouses(name,location) VALUES(?,?)",(data.name,data.location))
            record_event(c,"WAREHOUSE_CREATED","admin",{"name":data.name,"location":data.location})
            c.commit()
            return {"id":cur.lastrowid,"name":data.name}
        except sqlite3.IntegrityError: raise HTTPException(409,"Warehouse name already exists")

@app.get("/api/suppliers")
def suppliers():
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM suppliers ORDER BY id DESC").fetchall()]

@app.post("/api/suppliers")
def add_supplier(data: SupplierIn):
    with conn() as c:
        cur=c.execute("INSERT INTO suppliers(name,email) VALUES(?,?)",(data.name,data.email))
        record_event(c,"SUPPLIER_CREATED","admin",data.model_dump())
        c.commit()
        return {"id":cur.lastrowid,"name":data.name}

@app.get("/api/products")
def products():
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM products ORDER BY id").fetchall()]

@app.post("/api/products")
def add_product(data: ProductIn):
    with conn() as c:
        try:
            cur=c.execute("INSERT INTO products(sku,name,category,reorder_level) VALUES(?,?,?,?)",(data.sku,data.name,data.category,data.reorder_level))
            for w in c.execute("SELECT id FROM warehouses").fetchall():
                c.execute("INSERT INTO inventory(product_id,warehouse_id,quantity,updated_at) VALUES(?,?,0,?)",(cur.lastrowid,w["id"],now()))
            record_event(c,"PRODUCT_CREATED","admin",data.model_dump())
            c.commit()
            return {"id":cur.lastrowid,"sku":data.sku}
        except sqlite3.IntegrityError: raise HTTPException(409,"SKU already exists")

@app.get("/api/events")
def events():
    with conn() as c:
        rows=c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100").fetchall()
        return [{**dict(r),"payload":json.loads(r["payload"])} for r in rows]

@app.get("/api/alerts")
def alerts():
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 100").fetchall()]

@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id:int):
    with conn() as c:
        cur=c.execute("UPDATE alerts SET resolved=1 WHERE id=?",(alert_id,))
        if cur.rowcount==0: raise HTTPException(404,"Alert not found")
        c.commit()
        return {"success":True}

@app.get("/api/marketplaces")
def marketplaces():
    with conn() as c:
        return [dict(r) for r in c.execute("""SELECT m.*,p.sku,p.name product FROM marketplace_stock m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC""").fetchall()]

@app.post("/api/marketplaces")
def update_marketplace(data: MarketplaceIn):
    with conn() as c:
        c.execute("""INSERT INTO marketplace_stock(product_id,marketplace,quantity,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(product_id,marketplace) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at""",
        (data.product_id,data.marketplace,data.quantity,now()))
        record_event(c,"MARKETPLACE_STOCK_SYNC","marketplace_api",data.model_dump())
        c.commit()
        return {"success":True,"message":"Marketplace stock synchronized"}

@app.post("/api/reconcile")
def reconcile():
    changes=[]
    with conn() as c:
        rows=c.execute("""SELECT p.id product_id,p.name,w.id warehouse_id,w.name warehouse,
        i.quantity warehouse_qty,m.marketplace,m.quantity market_qty
        FROM inventory i JOIN products p ON p.id=i.product_id
        JOIN warehouses w ON w.id=i.warehouse_id
        JOIN marketplace_stock m ON m.product_id=p.id""").fetchall()
        # Demo policy: marketplace available stock is capped to total warehouse stock.
        totals=c.execute("SELECT product_id,SUM(quantity) total FROM inventory GROUP BY product_id").fetchall()
        total_map={r["product_id"]:r["total"] for r in totals}
        seen=set()
        for r in rows:
            key=(r["product_id"],r["marketplace"])
            if key in seen: continue
            seen.add(key)
            safe=max(0,total_map.get(r["product_id"],0))
            if r["market_qty"]>safe:
                c.execute("UPDATE marketplace_stock SET quantity=?,updated_at=? WHERE product_id=? AND marketplace=?",
                          (safe,now(),r["product_id"],r["marketplace"]))
                changes.append({"product":r["name"],"marketplace":r["marketplace"],"old":r["market_qty"],"new":safe})
        record_event(c,"INVENTORY_RECONCILIATION","reconciliation_engine",{"changes":changes,"policy":"Marketplace stock cannot exceed total warehouse stock"})
        c.commit()
    return {"success":True,"changes":changes,"reconciled_records":len(changes)}

@app.get("/api/analytics")
def analytics():
    with conn() as c:
        rows=c.execute("""SELECT p.name,p.sku,SUM(i.quantity) total FROM products p
        LEFT JOIN inventory i ON i.product_id=p.id GROUP BY p.id ORDER BY total DESC""").fetchall()
        return [dict(r) for r in rows]
