"""C3-B release hygiene scanner behavior."""

from check_release_hygiene import scan_text


def test_hygiene_accepts_placeholders_and_redacted_release_artifacts():
    assert scan_text("codeaware-py/.env.example", "LLM_API_KEY=sk-your-deepseek-api-key") == []
    assert scan_text(
        "docs/roadmap/current-release/evidence/C3/report.md",
        "root=<repo_root> key=sk-<redacted>",
    ) == []


def test_hygiene_rejects_real_key_and_private_key():
    findings = scan_text(
        "app.py",
        "token=" + "sk-" + "abcdefghijklmnopqrstuv\n"
        + "-----BEGIN "
        + "PRIVATE KEY-----",
    )
    assert "app.py: api-key" in findings
    assert "app.py: private-key" in findings


def test_hygiene_rejects_release_host_path_and_connection_string():
    path = "docs/roadmap/current-release/evidence/C3/artifacts/run.log"
    findings = scan_text(
        path,
        "cwd=/Users/alice/project db="
        + "postgresql:"
        + "//user:secret@localhost/app",
    )
    assert f"{path}: host-path" in findings
    assert f"{path}: connection-string" in findings


def test_hygiene_does_not_treat_general_documented_url_as_release_artifact_leak():
    assert scan_text(
        "README.md",
        "local example redis://localhost:6380/0",
    ) == []
