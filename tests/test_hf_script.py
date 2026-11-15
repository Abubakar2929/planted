"""scripts/push_hf_dataset.py: checks on the real files (dry run) and on fake bad pages. Never pushes."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("push_hf_dataset", ROOT / "scripts" / "push_hf_dataset.py")
hf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hf)


@pytest.fixture(autouse=True)
def no_upload(monkeypatch):
    import huggingface_hub

    def boom(*a, **kw):
        raise AssertionError("no uploads in tests")

    monkeypatch.setattr(huggingface_hub.HfApi, "upload_folder", boom, raising=False)
    monkeypatch.setattr(huggingface_hub.HfApi, "create_repo", boom, raising=False)


@pytest.mark.skipif(not (ROOT / "data" / "questions" / "dev20.jsonl").exists(), reason="no data")
def test_real_files_pass_checks_in_dry_run(capsys):
    files = hf.collect(ROOT)
    names = {f.as_posix() for f in files}
    assert "data/questions/dev20.jsonl" in names and "data/pages/main/pages.jsonl" in names
    assert not any(n.endswith(".py") for n in names)  # outputs only, no generator code
    stats = hf.run_checks(ROOT, files)
    assert stats["urls_checked"] > 1000
    assert hf.main(["--repo", "org/planted"]) == 0  # dry run is the default
    out = capsys.readouterr().out
    assert "checks passed" in out and "dry run: nothing uploaded" in out and "README.md" in out


def _bank(tmp_path, url, domain=None, extra=""):
    d = tmp_path / "data" / "pages" / "main"
    d.mkdir(parents=True)
    rec = {"url": url, "domain": domain or url.split("/")[2], "title": "t", "body": "b" + extra}
    (d / "pages.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return [Path("data/pages/main/pages.jsonl")]


def test_good_fake_page_passes(tmp_path):
    files = _bank(tmp_path, "https://ok-news.example/q1/a")
    assert hf.run_checks(tmp_path, files)["urls_checked"] == 1


@pytest.mark.parametrize("url,domain", [("https://realnews.com/q1/a", None),
                                        ("https://ok.example/q1/a", "realnews.com")])
def test_non_example_domain_fails(tmp_path, url, domain):
    files = _bank(tmp_path, url, domain)
    with pytest.raises(hf.CheckError, match="not .example"):
        hf.run_checks(tmp_path, files)


@pytest.mark.parametrize("secret", ["GEMINI_API_KEY=x", "AIza" + "A" * 35, "gsk_" + "a1" * 15])
def test_secret_strings_fail(tmp_path, secret):
    files = _bank(tmp_path, "https://ok.example/q1/a", extra=secret)
    with pytest.raises(hf.CheckError, match="contains"):
        hf.run_checks(tmp_path, files)


def test_card_is_written(tmp_path):
    files = _bank(tmp_path, "https://ok.example/q1/a")
    dest = tmp_path / "stage"
    hf.stage(tmp_path, files, dest)
    card = (dest / "README.md").read_text(encoding="utf-8")
    assert "license: mit" in card and "fictional" in card and "data/pages/main/pages.jsonl" in card
    assert (dest / "data/pages/main/pages.jsonl").exists()
