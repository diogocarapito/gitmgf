from app.services.passwords import hash_password, password_problem, verify_password


def test_hash_and_verify():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!!", stored)
    assert hash_password("same") != hash_password("same")  # salted


def test_unknown_account_and_garbage_never_verify():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_password_rules():
    assert password_problem("short")
    assert password_problem("ana@example.org", "ana@example.org")
    assert password_problem("a-long-enough-pass") is None
