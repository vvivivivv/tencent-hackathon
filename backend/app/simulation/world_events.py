"""
world_events.py — writes granular, frontend-consumable events during a run.

Every function here inserts one row into the `events` table with:
  type:     "WORLD_<EVENT_NAME>" — matches the frontend WorldEvent union
  metadata: run_id + whatever fields that WorldEvent variant needs

The frontend subscribes to `events` via Supabase Realtime, filtered by
run_id, and maps each row 1:1 onto WorldEventBus.emit(). This is what
makes the pixel world during a Custom Stress Test reflect what the real
Investigator/Operator are actually doing — not a scripted proxy.
"""

from __future__ import annotations
import time
import hashlib
import traceback

_COLORS = [0xff9f69, 0x69c3ff, 0xb5ff69, 0xffd169, 0xe069ff, 0x69ffe0, 0xff69b4, 0x69ffb4]

def color_for(name: str) -> int:
    """Deterministic color per customer name, so re-renders stay consistent."""
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return _COLORS[h % len(_COLORS)]


def _emit(db, run_id: str, event_type: str, **fields) -> None:

    if db is None:
        print("[WORLD EVENT] db is None")
        return

    payload = {
        "type": f"WORLD_{event_type}",
        "metadata": {
            "run_id": run_id,
            **fields,
        },
    }

    print(
        f"[WORLD EVENT INSERT] "
        f"type={payload['type']} "
        f"run_id={run_id}"
    )

    try:

        result = (
            db
            .table("events")
            .insert(payload)
            .execute()
        )

        print(
            f"[WORLD EVENT INSERTED] "
            f"type={payload['type']} "
            f"result={result.data}"
        )

    except Exception as e:

        print(
            f"[WORLD EVENT ERROR] "
            f"type={payload['type']} "
            f"error={e}"
        )

        traceback.print_exc()


def emit_customer_journey(db, run_id: str, journey: dict, step_delay: float = 0.9) -> None:
    cid = journey.get("customer_id") or journey.get("name") or "unknown"
    color = color_for(cid)
    device = journey.get("device", "desktop")
    customer_type = journey.get("customer_type", "returning")

    zones = ["aisle_left", "aisle_center", "aisle_right"]
    browse_zone = zones[int(hashlib.md5(cid.encode()).hexdigest(), 16) % len(zones)]

    _emit(db, run_id, "CUSTOMER_ENTER", customerId=cid, color=color, device=device, customerType=customer_type)
    time.sleep(step_delay)

    _emit(db, run_id, "CUSTOMER_BROWSE", customerId=cid, zone=browse_zone)
    time.sleep(step_delay)

    _emit(db, run_id, "CUSTOMER_PICK", customerId=cid, product=journey.get("goal", "item"))
    time.sleep(step_delay)

    _emit(db, run_id, "CUSTOMER_QUEUE", customerId=cid)
    time.sleep(step_delay)

    _emit(db, run_id, "CUSTOMER_CHECKOUT", customerId=cid, total=journey.get("total", 0), fee=journey.get("fee"))
    time.sleep(step_delay)

    if journey.get("result") == "completed":
        _emit(db, run_id, "CUSTOMER_SUCCESS", customerId=cid)
    else:
        bubble = journey.get("reason") or "Not happy about this... 😠"
        _emit(db, run_id, "CUSTOMER_ABANDON", customerId=cid, reason=journey.get("reason", ""), bubble=bubble[:40])
    time.sleep(step_delay)

    _emit(db, run_id, "CUSTOMER_EXIT", customerId=cid)


def emit_anomaly_alert(db, run_id: str, message: str) -> None:
    _emit(db, run_id, "ANOMALY_ALERT", message=message)


def emit_agent_move(db, run_id: str, target: str) -> None:
    _emit(db, run_id, "AGENT_MOVE", target=target)


def emit_agent_speak(db, run_id: str, text: str) -> None:
    _emit(db, run_id, "AGENT_SPEAK", text=text)


def emit_agent_fix_apply(db, run_id: str, label: str) -> None:
    _emit(db, run_id, "AGENT_FIX_APPLY", feeFrom=0, feeTo=0, label=label)


def emit_agent_verify(db, run_id: str) -> None:
    _emit(db, run_id, "AGENT_VERIFY", message="Verifying fix is live...")


def emit_metrics_update(db, run_id: str, abandonment_pct: int, conversion_pct: int) -> None:
    _emit(db, run_id, "METRICS_UPDATE", abandonment=abandonment_pct, conversion=conversion_pct)


def emit_incident_resolved(db, run_id: str) -> None:
    _emit(db, run_id, "INCIDENT_RESOLVED")