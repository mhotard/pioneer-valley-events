"""Offline storage and recovery tests for both Fabulous 413 miners."""

import json

import pytest

import fab413_common
import fab413_entities
import fab413_guide
import fab413_miner
import fab413_stats
from json_storage import JsonStorageError

MINERS = [fab413_miner, fab413_entities]


def episode(guid, episode_date="2026-08-01", **changes):
    value = {
        "guid": guid,
        "date": episode_date,
        "title": f"Episode {guid}",
        "link": f"https://example.com/{guid}",
        "text": f"Description for {guid}",
    }
    value.update(changes)
    return value


def result_key(module):
    return "mentions" if module is fab413_miner else "entities"


def empty_checkpoint(module):
    return {"mined_guids": [], result_key(module): []}


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def configure_main(monkeypatch, tmp_path, module, episodes, mine_batch, batch_size=2):
    output_path = tmp_path / f"{module.__name__}-checkpoint.json"
    episodes_path = tmp_path / f"{module.__name__}-episodes.json"
    monkeypatch.setattr(module, "BATCH_SIZE", batch_size)
    monkeypatch.setattr(module, "mine_batch", mine_batch)
    if module is fab413_miner:
        monkeypatch.setattr(module, "fetch_feed", lambda: episodes)
    else:
        write_json(
            episodes_path,
            {"count": len(episodes), "episodes": episodes},
        )
    return output_path, episodes_path


class TestEpisodeSnapshots:
    def test_missing_snapshot_creates_envelope_and_count(self, tmp_path):
        path = tmp_path / "episodes.json"
        episodes = [episode("new", title="Café episode")]

        assert fab413_miner.save_episodes(episodes, path) == 1

        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored == {"count": 1, "episodes": episodes}
        assert "Café episode" in path.read_text(encoding="utf-8")

    def test_merge_retains_old_refreshes_known_and_sorts_newest_first(self, tmp_path):
        path = tmp_path / "episodes.json"
        old = episode("old", "2026-07-01")
        refreshed = episode("same", "2026-06-01", text="old details")
        write_json(path, {"count": 2, "episodes": [old, refreshed]})
        incoming = [
            episode("same", "2026-08-01", text="new details"),
            episode("new", "2026-09-01", title="Été"),
        ]

        assert fab413_miner.save_episodes(incoming, path) == 3

        stored = json.loads(path.read_text(encoding="utf-8"))
        assert [item["guid"] for item in stored["episodes"]] == ["new", "same", "old"]
        assert stored["episodes"][1]["text"] == "new details"
        assert "Été" in path.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "stored",
        [
            None,
            [],
            {},
            {"episodes": None},
            {"episodes": [[]]},
            {"episodes": [{"guid": "only-a-guid"}]},
        ],
    )
    def test_unsafe_snapshot_fails_without_replacement(self, tmp_path, stored):
        path = tmp_path / "episodes.json"
        before = json.dumps(stored).encode()
        path.write_bytes(before)

        with pytest.raises(ValueError, match=str(path)):
            fab413_miner.save_episodes([episode("new")], path)

        assert path.read_bytes() == before

    def test_corrupt_snapshot_fails_without_replacement(self, tmp_path):
        path = tmp_path / "episodes.json"
        path.write_bytes(b"{corrupt snapshot")

        with pytest.raises(JsonStorageError, match=str(path)):
            fab413_miner.save_episodes([episode("new")], path)

        assert path.read_bytes() == b"{corrupt snapshot"

    def test_unreadable_snapshot_fails_without_replacement(
        self, monkeypatch, tmp_path
    ):
        path = tmp_path / "episodes.json"
        path.write_bytes(b"historical snapshot")

        def deny_read(*args, **kwargs):
            raise PermissionError(f"cannot read {path}")

        monkeypatch.setattr(fab413_miner, "read_json", deny_read)
        with pytest.raises(PermissionError, match=str(path)):
            fab413_miner.save_episodes([episode("new")], path)

        assert path.read_bytes() == b"historical snapshot"

    def test_duplicate_stored_guids_are_rejected(self, tmp_path):
        path = tmp_path / "episodes.json"
        duplicate = episode("same")
        before = json.dumps({"episodes": [duplicate, duplicate]}).encode()
        path.write_bytes(before)

        with pytest.raises(ValueError, match="Duplicate episode guid"):
            fab413_miner.save_episodes([episode("new")], path)

        assert path.read_bytes() == before

    def test_replacement_failure_preserves_snapshot_bytes(
        self, monkeypatch, tmp_path
    ):
        path = tmp_path / "episodes.json"
        stored = {"count": 1, "episodes": [episode("old")]}
        before = json.dumps(stored, separators=(",", ":")).encode()
        path.write_bytes(before)

        def fail_write(*args, **kwargs):
            raise OSError("replace failed")

        monkeypatch.setattr(fab413_miner, "write_json_atomic", fail_write)
        with pytest.raises(OSError, match="replace failed"):
            fab413_miner.save_episodes([episode("new")], path)

        assert path.read_bytes() == before

    def test_required_corpus_rejects_missing_and_invalid(self, tmp_path):
        missing = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            fab413_entities.load_episodes(missing)

        invalid = tmp_path / "invalid.json"
        write_json(invalid, {})
        with pytest.raises(ValueError, match=str(invalid)):
            fab413_entities.load_episodes(invalid)

        corrupt = tmp_path / "corrupt.json"
        corrupt.write_bytes(b"{corrupt corpus")
        with pytest.raises(JsonStorageError, match=str(corrupt)):
            fab413_entities.load_episodes(corrupt)


@pytest.mark.parametrize("module", MINERS, ids=lambda module: module.__name__)
class TestMiningCheckpoints:
    def test_missing_checkpoint_returns_valid_fresh_envelopes(self, module, tmp_path):
        path = tmp_path / "missing.json"

        first = module.load_store(path)
        second = module.load_store(path)
        first[result_key(module)].append({"changed": True})

        assert second == empty_checkpoint(module)

    @pytest.mark.parametrize("stored", [None, [], {}, {"mined_guids": [], "bad": []}])
    def test_invalid_checkpoint_is_rejected_unchanged(self, module, tmp_path, stored):
        path = tmp_path / "checkpoint.json"
        before = json.dumps(stored).encode()
        path.write_bytes(before)

        with pytest.raises(ValueError, match=str(path)):
            module.load_store(path)

        assert path.read_bytes() == before

    def test_checkpoint_requires_string_guids_and_object_rows(self, module, tmp_path):
        key = result_key(module)
        path = tmp_path / "checkpoint.json"

        for value in (
            {"mined_guids": [1], key: []},
            {"mined_guids": [], key: ["not-an-object"]},
        ):
            write_json(path, value)
            with pytest.raises(ValueError, match=str(path)):
                module.load_store(path)

    def test_fresh_checkpoint_saves_rows_and_guids_together(
        self, module, monkeypatch, tmp_path
    ):
        episodes = [episode("one"), episode("two")]
        output_path, episodes_path = configure_main(
            monkeypatch,
            tmp_path,
            module,
            episodes,
            lambda batch: [{"batch": [item["guid"] for item in batch]}],
        )

        module.main([], output_path=output_path, episodes_path=episodes_path)

        stored = json.loads(output_path.read_text(encoding="utf-8"))
        assert stored["mined_guids"] == ["one", "two"]
        assert stored[result_key(module)] == [{"batch": ["one", "two"]}]

    def test_already_mined_episodes_never_reach_extraction(
        self, module, monkeypatch, tmp_path
    ):
        episodes = [episode("one"), episode("two"), episode("three")]
        calls = []

        def mine(batch):
            calls.append([item["guid"] for item in batch])
            return [{"batch": calls[-1]}]

        output_path, episodes_path = configure_main(
            monkeypatch, tmp_path, module, episodes, mine
        )
        existing = empty_checkpoint(module)
        existing["mined_guids"] = ["one"]
        existing[result_key(module)] = [{"batch": ["one"]}]
        write_json(output_path, existing)

        module.main([], output_path=output_path, episodes_path=episodes_path)

        assert calls == [["two", "three"]]
        stored = json.loads(output_path.read_text(encoding="utf-8"))
        assert stored["mined_guids"] == ["one", "two", "three"]
        assert stored[result_key(module)][0] == {"batch": ["one"]}

    def test_successful_empty_batch_still_checkpoints_guids(
        self, module, monkeypatch, tmp_path
    ):
        episodes = [episode("one"), episode("two")]
        output_path, episodes_path = configure_main(
            monkeypatch, tmp_path, module, episodes, lambda _batch: []
        )

        module.main([], output_path=output_path, episodes_path=episodes_path)

        stored = json.loads(output_path.read_text(encoding="utf-8"))
        assert stored == {"mined_guids": ["one", "two"], result_key(module): []}

    def test_extraction_failure_does_not_checkpoint_failed_batch_and_later_succeeds(
        self, module, monkeypatch, tmp_path
    ):
        episodes = [episode("failed"), episode("saved")]
        calls = []

        def mine(batch):
            guid = batch[0]["guid"]
            calls.append(guid)
            if guid == "failed":
                raise RuntimeError("extraction failed")
            return [{"batch": guid}]

        output_path, episodes_path = configure_main(
            monkeypatch, tmp_path, module, episodes, mine, batch_size=1
        )

        module.main([], output_path=output_path, episodes_path=episodes_path)

        stored = json.loads(output_path.read_text(encoding="utf-8"))
        assert calls == ["failed", "saved"]
        assert stored["mined_guids"] == ["saved"]
        assert stored[result_key(module)] == [{"batch": "saved"}]

    def test_second_save_failure_then_restart_retries_only_uncommitted_work(
        self, module, monkeypatch, tmp_path
    ):
        episodes = [episode("one"), episode("two"), episode("three")]
        calls = []

        def mine(batch):
            guid = batch[0]["guid"]
            calls.append(guid)
            return [{"batch": guid}]

        output_path, episodes_path = configure_main(
            monkeypatch, tmp_path, module, episodes, mine, batch_size=1
        )
        real_save = module.save_store
        saves = 0

        def fail_second_save(store, path=None):
            nonlocal saves
            saves += 1
            if saves == 2:
                raise OSError("replace interrupted")
            real_save(store, path)

        monkeypatch.setattr(module, "save_store", fail_second_save)

        with pytest.raises(OSError, match="replace interrupted"):
            module.main([], output_path=output_path, episodes_path=episodes_path)

        first_checkpoint_bytes = output_path.read_bytes()
        first_checkpoint = json.loads(first_checkpoint_bytes)
        assert calls == ["one", "two"]
        assert first_checkpoint == {
            "mined_guids": ["one"],
            result_key(module): [{"batch": "one"}],
        }

        calls.clear()
        monkeypatch.setattr(module, "save_store", real_save)
        module.main([], output_path=output_path, episodes_path=episodes_path)

        stored = json.loads(output_path.read_text(encoding="utf-8"))
        assert calls == ["two", "three"]
        assert stored["mined_guids"] == ["one", "two", "three"]
        assert stored[result_key(module)] == [
            {"batch": "one"},
            {"batch": "two"},
            {"batch": "three"},
        ]
        assert first_checkpoint_bytes != output_path.read_bytes()

    def test_corrupt_checkpoint_fails_before_feed_corpus_or_extraction(
        self, module, monkeypatch, tmp_path, capsys
    ):
        output_path = tmp_path / "checkpoint.json"
        episodes_path = tmp_path / "episodes.json"
        output_path.write_bytes(b"{corrupt checkpoint")

        def unexpected(*args, **kwargs):
            pytest.fail("damaged checkpoint allowed new work")

        monkeypatch.setattr(module, "mine_batch", unexpected)
        if module is fab413_miner:
            monkeypatch.setattr(module, "fetch_feed", unexpected)
        else:
            monkeypatch.setattr(module, "load_episodes", unexpected)

        with pytest.raises(JsonStorageError, match=str(output_path)):
            module.main([], output_path=output_path, episodes_path=episodes_path)

        assert output_path.read_bytes() == b"{corrupt checkpoint"
        assert "Done:" not in capsys.readouterr().out

    def test_unreadable_checkpoint_fails_before_extraction(
        self, module, monkeypatch, tmp_path
    ):
        output_path = tmp_path / "checkpoint.json"
        output_path.write_bytes(b"preserved")

        def deny_read(path, **kwargs):
            raise PermissionError(f"cannot read {path}")

        def unexpected(*args, **kwargs):
            pytest.fail("unreadable checkpoint allowed new work")

        monkeypatch.setattr(module, "read_json", deny_read)
        monkeypatch.setattr(module, "mine_batch", unexpected)
        with pytest.raises(PermissionError, match=str(output_path)):
            module.main([], output_path=output_path, episodes_path=tmp_path / "episodes.json")

        assert output_path.read_bytes() == b"preserved"

    def test_limit_and_no_work_behavior(self, module, monkeypatch, tmp_path):
        episodes = [episode("one"), episode("two"), episode("three")]
        calls = []

        def mine(batch):
            calls.append([item["guid"] for item in batch])
            return []

        output_path, episodes_path = configure_main(
            monkeypatch, tmp_path, module, episodes, mine, batch_size=1
        )
        module.main(
            ["--limit", "2"], output_path=output_path, episodes_path=episodes_path
        )
        assert calls == [["one"], ["two"]]

        def fail_mine(_batch):
            pytest.fail("fully mined checkpoint attempted extraction")

        module.main(
            ["--limit", "2"], output_path=output_path, episodes_path=episodes_path
        )
        assert calls == [["one"], ["two"], ["three"]]

        monkeypatch.setattr(module, "mine_batch", fail_mine)
        module.main(
            ["--limit", "2"], output_path=output_path, episodes_path=episodes_path
        )
        assert json.loads(output_path.read_text())["mined_guids"] == [
            "one",
            "two",
            "three",
        ]


@pytest.mark.parametrize("module", MINERS, ids=lambda module: module.__name__)
def test_miner_aborts_after_three_consecutive_failures_with_progress_saved(
    module, monkeypatch, tmp_path
):
    episodes = [episode(guid) for guid in ("saved", "bad-1", "bad-2", "bad-3", "later")]

    def mine(batch):
        guid = batch[0]["guid"]
        if guid.startswith("bad"):
            raise RuntimeError("API unavailable")
        return [{"batch": guid}]

    output_path, episodes_path = configure_main(
        monkeypatch, tmp_path, module, episodes, mine, batch_size=1
    )

    with pytest.raises(SystemExit) as exc_info:
        module.main([], output_path=output_path, episodes_path=episodes_path)

    assert exc_info.value.code == 1
    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored == {
        "mined_guids": ["saved"],
        result_key(module): [{"batch": "saved"}],
    }


@pytest.mark.parametrize("module", MINERS, ids=lambda module: module.__name__)
def test_miner_success_resets_consecutive_failure_counter(module, monkeypatch, tmp_path):
    sequence = ("bad-1", "bad-2", "saved-1", "bad-3", "bad-4", "saved-2")
    episodes = [episode(guid) for guid in sequence]

    def mine(batch):
        guid = batch[0]["guid"]
        if guid.startswith("bad"):
            raise RuntimeError("API unavailable")
        return [{"batch": guid}]

    output_path, episodes_path = configure_main(
        monkeypatch, tmp_path, module, episodes, mine, batch_size=1
    )

    module.main([], output_path=output_path, episodes_path=episodes_path)

    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored["mined_guids"] == ["saved-1", "saved-2"]
    assert stored[result_key(module)] == [{"batch": "saved-1"}, {"batch": "saved-2"}]


def test_render_batch_matches_the_prompt_contract():
    batch = [
        episode("a", "2026-01-02", title="First", text="Hello there"),
        episode("b", "2026-01-09", title="Second", text="More text"),
    ]
    assert fab413_common.render_batch(batch) == (
        "[Episode 0 | 2026-01-02 | First]\nHello there\n\n"
        "[Episode 1 | 2026-01-09 | Second]\nMore text"
    )


def test_guide_and_stats_write_through_the_atomic_helper(monkeypatch, tmp_path):
    writes = []

    def record(path, value, **kwargs):
        writes.append((str(path), value, kwargs))

    mentions_path = tmp_path / "mentions.json"
    write_json(mentions_path, {"mined_guids": [], "mentions": []})
    monkeypatch.setattr(fab413_guide, "curate", lambda cands: [])
    monkeypatch.setattr(fab413_guide, "write_json_atomic", record)
    guide_out = tmp_path / "seasonal.json"
    fab413_guide.main(mentions_path=mentions_path, output_path=guide_out)

    entities_path = tmp_path / "entities.json"
    episodes_path = tmp_path / "episodes.json"
    write_json(entities_path, {"mined_guids": [], "entities": []})
    write_json(episodes_path, {"count": 0, "episodes": []})
    monkeypatch.setattr(fab413_stats, "write_json_atomic", record)
    stats_out = tmp_path / "413" / "data.json"
    fab413_stats.main(
        entities_path=entities_path, episodes_path=episodes_path, output_path=stats_out
    )

    assert [w[0] for w in writes] == [str(guide_out), str(stats_out)]
    assert all(w[2] == {"separators": (",", ":")} for w in writes)
    assert set(writes[0][1]["months"]) == {str(m) for m in range(1, 13)}
    assert writes[1][1]["totals"]["episodes"] == 0
