"""UnraidMonitor parsing + condition logic (issue #30)."""
from app.config import UnraidConfig
from app.services.unraid_monitor import (
    UnraidMonitor,
    UnraidStatus,
    evaluate_status,
    compute_unraid_reasons,
)


def _payload(state="STARTED", parity_status="NEVER_RUN", mover=False, disk_status="DISK_OK"):
    return {
        "array": {
            "state": state,
            "parityCheckStatus": {"status": parity_status, "running": parity_status == "RUNNING", "progress": 42},
            "disks": [{"status": disk_status, "type": "DATA"}],
            "parities": [{"status": "DISK_OK", "type": "PARITY"}],
        },
        "vars": {"shareMoverActive": mover},
    }


def test_evaluate_parity_running():
    s = evaluate_status(_payload(parity_status="RUNNING"))
    assert s.parity_running is True
    assert s.parity_progress == 42
    assert s.mover_active is False
    assert s.array_degraded is False


def test_evaluate_mover_active():
    s = evaluate_status(_payload(mover=True))
    assert s.mover_active is True
    assert s.parity_running is False


def test_evaluate_array_degraded_by_state():
    assert evaluate_status(_payload(state="STOPPED")).array_degraded is True


def test_evaluate_array_degraded_by_disk():
    assert evaluate_status(_payload(disk_status="DISK_DSBL")).array_degraded is True


def test_evaluate_all_clear():
    s = evaluate_status(_payload())
    assert (s.parity_running, s.mover_active, s.array_degraded) == (False, False, False)


def test_evaluate_null_safe():
    s = evaluate_status(None)
    assert (s.parity_running, s.mover_active, s.array_degraded) == (False, False, False)
    assert s.array_state == "UNKNOWN"
    s2 = evaluate_status({})
    assert s2.array_degraded is True  # missing state -> not "STARTED"


def test_reasons_honor_toggles():
    status = UnraidStatus(parity_running=True, mover_active=True, array_degraded=True,
                          array_state="STARTED", parity_progress=None)
    all_on = UnraidConfig(throttle_on_parity_check=True, throttle_on_mover=True, throttle_on_array_degraded=True)
    assert compute_unraid_reasons(status, all_on) == ["parity_check", "mover", "array_degraded"]

    only_mover = UnraidConfig(throttle_on_parity_check=False, throttle_on_mover=True, throttle_on_array_degraded=False)
    assert compute_unraid_reasons(status, only_mover) == ["mover"]


def test_endpoint_appends_graphql():
    assert UnraidMonitor(UnraidConfig(url="http://tower:80"))._endpoint() == "http://tower:80/graphql"
    assert UnraidMonitor(UnraidConfig(url="http://tower/graphql/"))._endpoint() == "http://tower/graphql"
