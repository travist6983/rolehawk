from rolehawk import __version__


def status() -> dict[str, str]:
    """Return basic service health. Placeholder until Chunk 2 adds real checks."""
    return {"status": "ok", "version": __version__}
