# StockFlow — Distributed Inventory Data Processing System

A runnable college-project prototype for retail and e-commerce inventory processing. It demonstrates a multi-warehouse inventory model, supplier/product masters, marketplace stock feeds, reconciliation, low-stock alerts, and an auditable event stream.

## Quick start (Mac / Windows / VS Code)

**Requirements:** Python 3.10 or newer.

1. Extract this ZIP.
2. Open the extracted `distributed-inventory-system` folder in VS Code.
3. Open VS Code Terminal (**Terminal → New Terminal**).
4. Run:

### macOS / Linux
```bash
chmod +x start.sh
./start.sh
```

### Windows
```bat
start.bat
```

5. Open **http://127.0.0.1:8000** in your browser.

The first launch creates a local SQLite database at `data/inventory.db` and inserts demo records. To reset demo data, stop the server and delete `data/inventory.db`, then start again.

## What works

- Overview dashboard and inventory analytics
- Multiple warehouse records
- Supplier and product management
- Stock adjustment API with audit events
- Marketplace stock feed endpoint
- Reconciliation rule: marketplace listed stock is capped at the product's total warehouse stock
- Automatic low-stock alerts and alert resolution
- Event log with source, status, timestamp and payload
- REST API and health check

## API quick reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service health |
| GET | `/api/dashboard` | KPI summary |
| GET | `/api/inventory` | Stock by product and warehouse |
| POST | `/api/stock` | Update stock and write event |
| GET/POST | `/api/warehouses` | List / create warehouse |
| GET/POST | `/api/suppliers` | List / create supplier |
| GET/POST | `/api/products` | List / create product |
| GET | `/api/events` | Processing audit log |
| GET | `/api/alerts` | Alerts |
| POST | `/api/alerts/{id}/resolve` | Resolve alert |
| GET/POST | `/api/marketplaces` | List / ingest marketplace stock |
| POST | `/api/reconcile` | Run reconciliation |
| GET | `/api/analytics` | Product stock totals |

Interactive API docs: **http://127.0.0.1:8000/docs**

## Architecture mapping to the approved proposal

```text
Suppliers / Warehouses / Marketplaces
                |
                v
       Data Ingestion API
                |
        Event / Audit Log
                |
                v
      Processing & Reconciliation
                |
                v
       Inventory Data Store
                |
          REST API
                |
       Operations Dashboard
                |
          Alert Service
```

### Important implementation note

This ZIP is a **working prototype**, not a production deployment of the complete proposed distributed stack. It uses FastAPI and SQLite so it can be installed and demonstrated quickly on a student laptop. The event table demonstrates event capture/auditability, and the reconciliation endpoint demonstrates consistency logic. SQLite is not a distributed database, and the event table is not Apache Kafka.

The approved proposal's target stack is Python, Apache Kafka, Apache Flink, Apache Cassandra, Apache ZooKeeper and Spring Boot. For a genuine distributed deployment, the next engineering stage is to:
1. Replace the local event/audit write path with Kafka topics and consumer groups.
2. Implement Flink streaming jobs for event-time processing, deduplication and reconciliation.
3. Move inventory partitions to Cassandra and define replication/consistency settings.
4. Add ZooKeeper only if required by the selected Kafka/coordination deployment (modern Kafka KRaft deployments do not require ZooKeeper).
5. Add Spring Boot services if Java microservices are a hard project requirement.
6. Add authentication, authorization, idempotency keys, retries, dead-letter queues, metrics and automated tests.

## Demo flow (2–3 minutes)

1. Open Overview and point out total units, products, warehouses and alerts.
2. Open Inventory. Select a product and warehouse; set quantity to `2`; click Update stock.
3. Open Alerts and show the automatically generated low-stock alert.
4. Open Event Stream and show the `STOCK_UPDATED` event.
5. Open Marketplaces. Set a product's reported marketplace stock higher than the warehouse total; click Sync feed.
6. Click Run reconciliation and show the corrected marketplace quantity and reconciliation event.
7. Open `/docs` to demonstrate the REST API.

## Troubleshooting

- **`python` not found:** try `python3 --version`; install Python 3.10+ if needed.
- **Port 8000 busy:** stop the other process using it, or change `--port 8000` in `start.sh` / `start.bat`.
- **Install issue:** run `python3 -m pip install -r requirements.txt` (Mac) or `py -m pip install -r requirements.txt` (Windows).
- Keep the terminal running while using the dashboard.
