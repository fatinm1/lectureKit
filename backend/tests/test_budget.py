from budget import Budget

def test_concurrency_releases_after_request():
    b = Budget(10, 1)
    assert b.enter(now=0)
    assert not b.enter(now=1)
    b.leave()
    assert b.enter(now=2)

def test_rate_window_expires():
    b = Budget(1, 1)
    assert b.enter(now=0)
    b.leave()
    assert not b.enter(now=59)
    assert b.enter(now=60)
