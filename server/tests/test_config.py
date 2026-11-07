from core import config


def test_wm_char_apps_are_lowercased(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('wm_char_apps = ["WeiXin.exe", "Telegram.exe"]', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    assert config.load_wm_char_apps() == {"weixin.exe", "telegram.exe"}
