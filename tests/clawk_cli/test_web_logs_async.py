import asyncio
import threading

from clawk_cli.web_routers import logs


def test_get_logs_yields_while_reading_and_filtering(monkeypatch):
    from clawk_constants import get_clawk_home

    logs_dir = get_clawk_home() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "agent.log").write_text("fixture\n", encoding="utf-8")

    loop_ran = threading.Event()

    def blocking_read(*args, **kwargs):
        assert loop_ran.wait(2), "log reading blocked the event loop"
        return ["fixture"]

    import clawk_cli.logs

    monkeypatch.setattr(clawk_cli.logs, "_read_tail", blocking_read)

    async def exercise():
        asyncio.get_running_loop().call_soon(loop_ran.set)
        return await logs.get_logs(file="agent", lines=100)

    assert asyncio.run(exercise()) == {"file": "agent", "lines": ["fixture"]}
