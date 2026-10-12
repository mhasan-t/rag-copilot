from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from src.core.config import app_config

_HEADINGS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]


def chunk_markdown(title: str, markdown: str) -> list[str]:
    """Splits markdown by heading, then splits long sections; returns chunk texts ready to embed and store.

    Each chunk starts with its heading path (e.g. "Payments latency > Diagnose > Check deploys") so it still makes
    sense on its own, both to the embedding model and to the LLM reading search results.
    """
    sections = MarkdownHeaderTextSplitter(_HEADINGS, strip_headers=True).split_text(markdown)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=app_config.knowledge.chunk_max_chars, chunk_overlap=app_config.knowledge.chunk_overlap_chars
    )
    chunks = []
    for section in sections:
        headings = [section.metadata[key] for _, key in _HEADINGS if key in section.metadata]
        # The document title is usually also the h1; don't repeat it.
        path = " > ".join([title, *(heading for heading in headings if heading != title)])
        chunks.extend(f"{path}\n\n{piece}" for piece in splitter.split_text(section.page_content) if piece.strip())
    return chunks
