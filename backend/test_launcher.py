import deuscfo


def test_linux_dev_uses_native_npm_command(monkeypatch):
    looked_up = []
    monkeypatch.setattr(deuscfo.os, "name", "posix")
    monkeypatch.setattr(deuscfo.shutil, "which", lambda name: looked_up.append(name))

    command = deuscfo._services("dev")["frontend"]["command"]

    assert looked_up == ["npm"]
    assert command[0] == "npm"
