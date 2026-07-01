from app.storage import Storage


def test_new_job_id_is_32_hex(tmp_path):
    s = Storage(str(tmp_path))
    jid = s.new_job_id()
    assert len(jid) == 32
    assert all(c in "0123456789abcdef" for c in jid)


def test_url_for(tmp_path):
    s = Storage(str(tmp_path))
    assert s.url_for("abc") == "/files/abc.glb"


def test_valid_job_id(tmp_path):
    s = Storage(str(tmp_path))
    good = s.new_job_id()
    assert s.is_valid_job_id(good) is True
    assert s.is_valid_job_id("../etc/passwd") is False
    assert s.is_valid_job_id("ABC") is False  # uppercase not allowed
    assert s.is_valid_job_id("") is False


def test_write_exists_delete(tmp_path):
    s = Storage(str(tmp_path))
    jid = s.new_job_id()
    assert s.exists(jid) is False
    s.path_for(jid).write_bytes(b"glb")
    assert s.exists(jid) is True
    assert s.delete(jid) is True
    assert s.exists(jid) is False
    assert s.delete(jid) is False  # already gone


def test_output_dir_created(tmp_path):
    target = tmp_path / "nested" / "out"
    Storage(str(target))
    assert target.is_dir()
