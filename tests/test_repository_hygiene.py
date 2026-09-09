from pathlib import Path


def test_no_temporary_apply_workflows():
    workflow_dir = Path(".github/workflows")
    offenders = sorted(p.name for p in workflow_dir.glob("apply-*.yml"))
    assert offenders == [], f"temporary apply workflows must not be committed: {offenders}"


def test_generate_runtime_import_path():
    import main

    assert callable(main.main)
