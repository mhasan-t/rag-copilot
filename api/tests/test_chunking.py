from src.modules.knowledge.chunking import chunk_markdown


def test_chunks_carry_their_heading_path_without_repeating_the_title():
    markdown = "# Payments latency\n\nIntro.\n\n## Diagnose\n\n### Check deployments\n\nCompare with history.\n"

    chunks = chunk_markdown("Payments latency", markdown)

    assert chunks == [
        "Payments latency\n\nIntro.",
        "Payments latency > Diagnose > Check deployments\n\nCompare with history.",
    ]


def test_headings_inside_code_blocks_do_not_start_a_new_chunk():
    markdown = "## Restart\n\n```sh\n# not a heading\nkubectl rollout restart deploy/payments\n```\n"

    [chunk] = chunk_markdown("Runbook", markdown)

    assert chunk.startswith("Runbook > Restart\n\n")
    assert "# not a heading" in chunk and "kubectl rollout restart" in chunk


def test_long_sections_are_split_and_every_piece_keeps_the_heading_path():
    paragraphs = "\n\n".join(f"Step {number}: " + "check the dashboard and the logs. " * 10 for number in range(20))

    chunks = chunk_markdown("Runbook", f"## Long procedure\n\n{paragraphs}\n")

    assert len(chunks) > 1
    assert all(chunk.startswith("Runbook > Long procedure\n\n") for chunk in chunks)
    assert all(len(chunk) <= 1500 + len("Runbook > Long procedure\n\n") for chunk in chunks)
    assert "Step 19" in chunks[-1]
