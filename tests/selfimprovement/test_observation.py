import json

import pytest

from selfimprovement.observation import (
    JsonlIntegrityError,
    JsonlObservationSink,
    Observation,
    ObservationRecorder,
    SecretRedactor,
    SQLiteObservationStore,
    stable_fingerprint,
)


def test_secret_redactor_regex_catches_common_variants():
    redactor = SecretRedactor()
    payload = {
        "apiToken": "abc",
        "passwd": "def",
        "nested": {"client_key": "ghi", "safe": "visible"},
        "Authorization": "Bearer xyz",
    }

    assert redactor.redact(payload) == {
        "apiToken": "[REDACTED]",
        "passwd": "[REDACTED]",
        "nested": {"client_key": "[REDACTED]", "safe": "visible"},
        "Authorization": "[REDACTED]",
    }


def test_stable_fingerprint_ignores_volatile_fields():
    left = {"tool": "click", "args": {"ref": "e1"}, "timestamp": "1", "request_id": "a"}
    right = {"tool": "click", "args": {"ref": "e1"}, "timestamp": "2", "request_id": "b"}

    assert stable_fingerprint(left) == stable_fingerprint(right)


def test_sqlite_store_is_idempotent(tmp_path):
    store = SQLiteObservationStore(tmp_path / "obs.sqlite3")
    obs = Observation(id="fixed", event_type="after_step", payload={"x": 1})

    store.append(obs)
    store.append(obs.model_copy(update={"payload": {"x": 2}}))

    saved = store.get("fixed")
    assert saved is not None
    assert saved.payload == {"x": 2}
    assert len(store.list_recent()) == 1
    store.close()


def test_jsonl_strict_mode_rotates_corrupt_file_and_raises(tmp_path):
    path = tmp_path / "obs.jsonl"
    path.write_text('{"ok": true}\n{bad json\n', encoding="utf-8")
    sink = JsonlObservationSink(path, strict=True)

    with pytest.raises(JsonlIntegrityError) as excinfo:
        sink.append(Observation(event_type="after_step"))

    assert excinfo.value.corrupt_path is not None
    assert excinfo.value.corrupt_path.exists()
    assert not path.exists()


def test_jsonl_rotates_when_large(tmp_path):
    path = tmp_path / "obs.jsonl"
    path.write_text(Observation(event_type="old", payload={"x": "x" * 2048}).to_json_line(), encoding="utf-8")
    sink = JsonlObservationSink(path, strict=False, max_bytes=1024, fsync=False)

    sink.append(Observation(event_type="after_step"))

    backups = list(tmp_path.glob("obs.jsonl.*.bak"))
    assert backups
    assert list(sink.iter_observations())[0].event_type == "after_step"


def test_recorder_dual_writes_sanitized_payload(tmp_path):
    store = SQLiteObservationStore(tmp_path / "obs.sqlite3")
    sink = JsonlObservationSink(tmp_path / "obs.jsonl", fsync=False)
    recorder = ObservationRecorder(sqlite_store=store, jsonl_sink=sink)

    obs = recorder.record("after_step", context={"apiToken": "abc", "visible": 1})

    assert obs.payload == {"apiToken": "[REDACTED]", "visible": 1}
    assert store.get(obs.id) == obs
    assert list(sink.iter_observations()) == [obs]
    store.close()


def test_jsonl_written_as_valid_json(tmp_path):
    sink = JsonlObservationSink(tmp_path / "obs.jsonl", fsync=False)
    obs = Observation(event_type="after_step", payload={"a": 1})

    sink.append(obs)

    line = (tmp_path / "obs.jsonl").read_text(encoding="utf-8")
    assert json.loads(line)["event_type"] == "after_step"


@pytest.mark.asyncio
async def test_recorder_async(tmp_path):
    store = SQLiteObservationStore(tmp_path / "obs.sqlite3")
    recorder = ObservationRecorder(sqlite_store=store)

    obs = await recorder.record_async("after_step", context={"x": 1})

    assert store.get(obs.id) == obs
    store.close()
