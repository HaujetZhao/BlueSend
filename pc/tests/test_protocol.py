from protocol import DOWNLINK_CHUNK_LIMIT, downlink_chunk_size


def test_android_gatt_limit_is_clamped():
    # Windows 报告 514（MTU-3），Android 栈只收 <=512。
    assert downlink_chunk_size(514) == 512


def test_smaller_reported_size_is_kept():
    assert downlink_chunk_size(20) == 20
    assert DOWNLINK_CHUNK_LIMIT == 512
