from uproot.types import sha256


def test_str():
    assert (
        sha256("QtLo6rfELu4Cuvb958DjV+l9ueNT1Q5+")
        == "f46d5a0faa58bb3d28ec6773ac0671bca055756aa4e8f8fdfdbe56d28e59d12a"
    )


def test_bytes():
    assert (
        sha256(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f")
        == "be45cb2605bf36bebde684841a28f0fd43c69850a3dce5fedba69928ee3a8991"
    )
