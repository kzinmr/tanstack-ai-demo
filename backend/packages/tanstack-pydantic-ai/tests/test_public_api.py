def test_public_api_exports() -> None:
    import tanstack_pydantic_ai as api

    expected = {
        "TanStackAIAdapter",
        "TanStackEventStream",
        "RunStorePort",
        "InMemoryRunStore",
        "RunState",
        "StreamChunk",
        "StreamChunkType",
    }

    assert set(api.__all__) == expected
    for name in expected:
        assert getattr(api, name) is not None
