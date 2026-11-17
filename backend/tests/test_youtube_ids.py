import pytest

from utils.youtube import InvalidYouTubeUrlError, extract_youtube_video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/watch?v=jNQXAC9IVRw&t=42s",
        "https://youtu.be/jNQXAC9IVRw",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "  https://m.youtube.com/watch?v=jNQXAC9IVRw  ",
    ],
)
def test_extracts_id(url):
    assert extract_youtube_video_id(url) == "jNQXAC9IVRw"


@pytest.mark.parametrize("url", ["", "https://example.com/watch", "https://youtu.be/"])
def test_rejects_bad_urls(url):
    with pytest.raises(InvalidYouTubeUrlError):
        extract_youtube_video_id(url)
