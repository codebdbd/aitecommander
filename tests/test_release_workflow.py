from __future__ import annotations

from pathlib import Path


def _resolve_target(
    input_tag: str, release_tag: str, ref: str, ref_name: str
) -> tuple[str, str]:
    """Python equivalent of the PowerShell target reference resolution logic."""
    input_tag = input_tag.strip()
    release_tag = release_tag.strip()
    ref = ref.strip()
    ref_name = ref_name.strip()

    if input_tag:
        return input_tag, input_tag
    if release_tag:
        return release_tag, release_tag
    if ref.startswith("refs/tags/"):
        return ref, ref_name
    if ref:
        return ref, ""
    return "main", ""


def test_release_workflow_file_structure() -> None:
    workflow_path = Path(".github/workflows/release.yml")
    assert workflow_path.is_file(), "release.yml must exist"

    content = workflow_path.read_text(encoding="utf-8")

    # 1. Verification of Determine target reference step
    assert "id: target" in content
    assert "Determine target reference" in content
    assert '"ref=$targetRef" >> $env:GITHUB_OUTPUT' in content
    assert '"tag=$targetTag" >> $env:GITHUB_OUTPUT' in content

    # 2. Verification that actions/checkout uses target.outputs.ref
    assert "uses: actions/checkout@v4" in content
    assert "ref: ${{ steps.target.outputs.ref }}" in content

    # 3. Verification that softprops/action-gh-release uses target.outputs.tag
    assert "uses: softprops/action-gh-release@v2" in content
    assert "tag_name: ${{ steps.target.outputs.tag }}" in content
    assert "if: steps.target.outputs.tag != ''" in content


def test_target_resolution_scenarios() -> None:
    # Scenario 1: Manual workflow_dispatch with specified release_tag
    ref, tag = _resolve_target(
        input_tag="v1.1.5",
        release_tag="",
        ref="refs/heads/main",
        ref_name="main",
    )
    assert ref == "v1.1.5"
    assert tag == "v1.1.5"

    # Scenario 2: GitHub release event (published/released)
    ref, tag = _resolve_target(
        input_tag="",
        release_tag="v1.2.0",
        ref="refs/tags/v1.2.0",
        ref_name="v1.2.0",
    )
    assert ref == "v1.2.0"
    assert tag == "v1.2.0"

    # Scenario 3: Git push of a tag
    ref, tag = _resolve_target(
        input_tag="",
        release_tag="",
        ref="refs/tags/v1.3.0",
        ref_name="v1.3.0",
    )
    assert ref == "refs/tags/v1.3.0"
    assert tag == "v1.3.0"

    # Scenario 4: Manual dispatch on a branch without release_tag (test build)
    ref, tag = _resolve_target(
        input_tag="",
        release_tag="",
        ref="refs/heads/main",
        ref_name="main",
    )
    assert ref == "refs/heads/main"
    assert tag == ""  # Release publishing is skipped
