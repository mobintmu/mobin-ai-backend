# How do you process 10 billion records per month while keeping query latency in the milliseconds?

**Type:** YouTube Video

We break down the architectural overhaul of a telecom KPI platform that was struggling under the weight of massive data volumes. By moving away from flexible but expensive JSON-string storage to a flat columnar architecture in ClickHouse, we transformed a system that took minutes to respond into one that delivers results almost instantly.
Key highlights of the redesign include:

    Flat Columnar Storage: We moved from "one-size-fits-all" JSON blobs to dedicated columns for every counter, allowing ClickHouse to leverage its native columnar strengths and reduce I/O costs by two orders of magnitude.
    Automated Schema Evolution: To handle frequent vendor updates, we built a self-healing pipeline using Airflow that automatically discovers new counters and adds them to the database schema without manual intervention.
    Decoupled Ingestion with Kafka: By introducing a Kafka buffer, we successfully managed a massive insert rate of 14 million records per hour, removing the performance bottlenecks caused by synchronous writes.
    Pre-calculated KPIs: We shifted heavy arithmetic from request-time to scheduled background tasks, allowing a lightweight Go-based backend to serve pre-computed results with minimal resource overhead.

The ultimate takeaway for any large-scale analytics project? Flat beats nested at scale.
Check out the full article to see how we optimized for ClickHouse’s strengths and built a self-maintaining data pipeline.
