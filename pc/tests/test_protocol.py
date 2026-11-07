from bluetooth_input.protocol import (
    BENCH_BYTES,
    DOWNLINK_CHUNK_LIMIT,
    bench_payload,
    downlink_chunk_size,
)


def test_android_gatt_limit_is_clamped():
    # Windows 报告 514（MTU-3），Android 栈只收 <=512。
    assert downlink_chunk_size(514) == 512


def test_smaller_reported_size_is_kept():
    assert downlink_chunk_size(20) == 20
    assert DOWNLINK_CHUNK_LIMIT == 512


def test_bench_payload_is_ascii_of_exact_size():
    # 字符数必须等于字节数，否则「256 KB」的口径两端对不上。
    payload = bench_payload()
    assert len(payload) == BENCH_BYTES
    assert payload.isascii()


def test_bench_payload_differs_each_run():
    # 固定载荷换两片也验不出来，每次必须不同。
    assert bench_payload() != bench_payload()
