import json

from scripts.evaluate_chunks import load_cases


def test_chunk_evaluation_dataset_has_stable_ids(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "question": "test",
                "relevant_chunk_ids": [
                    "3c5d679c-823b-5f56-9792-2a04bc28b4af"
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(dataset)

    assert cases[0]["question"] == "test"
    assert cases[0]["relevant_chunk_ids"] == [
        "3c5d679c-823b-5f56-9792-2a04bc28b4af"
    ]
