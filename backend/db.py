import sqlite3
from pathlib import Path

from backend.contracts import CallRecord, Cost, TraceEvent


class Store:
    """Operational ledger and transactional campaign migrations."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS api_calls(
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS calls_run ON api_calls(run_id);
                CREATE TABLE IF NOT EXISTS trace_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS traces_run ON trace_events(run_id);
                INSERT OR IGNORE INTO migrations VALUES(1);
            """)
        self.migrate_campaigns()
        self.migrate_generation()
        self.migrate_art()
        self.migrate_optimization()
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=6").fetchone():
            sql = (Path(__file__).parent / "migrations/006_delivery.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(6);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=7").fetchone():
            sql = (Path(__file__).parent / "migrations/007_work.sql").read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(7);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=8").fetchone():
            sql = (Path(__file__).parent / "migrations/008_meta.sql").read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(8);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        for version, filename in [
            (9, "009_social_profiles.sql"),
            (10, "010_plans.sql"),
            (11, "011_history_compatibility.sql"),
            (12, "012_websites.sql"),
        ]:
            if self.connection.execute(
                "SELECT 1 FROM migrations WHERE version=?", (version,)
            ).fetchone():
                continue
            sql = (Path(__file__).parent / "migrations" / filename).read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + f"\nINSERT INTO migrations VALUES({version});\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

    def migrate_optimization(self):
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=5").fetchone():
            sql = (Path(__file__).parent / "migrations/005_optimization.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(5);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise
        from backend.optimization_repository import OptimizationRepository

        OptimizationRepository(self).recover()

    def migrate_art(self):
        if self.connection.execute("SELECT 1 FROM migrations WHERE version=4").fetchone():
            return
        sql = (Path(__file__).parent / "migrations/004_art.sql").read_text()
        try:
            self.connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(4);\nCOMMIT;"
            )
        except Exception:
            self.connection.rollback()
            raise

    def migrate_generation(self):
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=3").fetchone():
            sql = (Path(__file__).parent / "migrations/003_generation.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(3);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise
        # Single-worker profile. Restart never repeats an interrupted provider call.
        from backend.generation_repository import GenerationRepository

        GenerationRepository(self).recover()

    def migrate_campaigns(self):
        if self.connection.execute("SELECT 1 FROM migrations WHERE version=2").fetchone():
            return
        sql = (Path(__file__).parent / "migrations/002_campaigns.sql").read_text()
        try:
            self.connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(2);\nCOMMIT;"
            )
        except Exception:
            self.connection.rollback()
            raise

    def record(self, call: CallRecord):
        event = TraceEvent(
            id=0,
            trace_id=call.trace_id,
            run_id=call.run_id,
            timestamp=call.timestamp,
            event=call.status,
            message=f"{call.operation}: {call.status}",
        )
        with self.connection:
            self.connection.execute(
                "INSERT INTO api_calls VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (call.id, call.run_id, call.model_dump_json()),
            )
            self.connection.execute(
                "INSERT INTO trace_events(run_id,payload) VALUES(?,?)",
                (call.run_id, event.model_dump_json()),
            )

        if call.work_id and getattr(self, "work", None):
            job = self.work.get(call.work_id)
            decision = (
                "Rate limited; bounded Retry-After wait"
                if call.http_status == 429
                else f"{call.operation}: {call.status}"
            )
            self.work.event(job.campaign_id, "validation", decision, job.id)

    def calls(self) -> list[CallRecord]:
        return [
            CallRecord.model_validate_json(row[0])
            for row in self.connection.execute("SELECT payload FROM api_calls ORDER BY rowid")
        ]

    def traces(self) -> list[TraceEvent]:
        return [
            TraceEvent.model_validate_json(row[1]).model_copy(update={"id": row[0]})
            for row in self.connection.execute(
                "SELECT id,payload FROM trace_events ORDER BY id DESC LIMIT 50"
            )
        ]

    def cost(self) -> Cost:
        calls = [c for c in self.calls() if c.sent]
        live = [c for c in calls if c.mode == "live"]
        return Cost(
            calls=len(calls),
            mock_calls=sum(c.mode == "mock" for c in calls),
            known_list_price_estimate=sum(c.list_price_estimate_usd or 0 for c in live),
            unknown_cost_calls=sum(c.list_price_estimate_usd is None for c in live),
        )

    def close(self):
        self.connection.close()
