"""Smoke test: verify package structure imports correctly."""

def test_harness_import():
    import harness
    assert harness.__version__ == "0.1.0"

def test_engine_import():
    from harness import engine
    assert engine is not None

def test_capabilities_import():
    from harness import capabilities
    assert capabilities is not None

def test_flows_import():
    from harness import flows
    assert flows is not None
