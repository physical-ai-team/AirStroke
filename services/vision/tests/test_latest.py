import asyncio

from vision.latest import LatestSlots


def test_keeps_only_latest_frame():
    async def run():
        slots = LatestSlots()
        for i in range(5):
            slots.put("s1", f"frame{i}".encode())
        assert len(slots) == 1
        assert slots.dropped == 4
        assert await slots.get() == ("s1", b"frame4")

    asyncio.run(run())


def test_round_robin_between_sessions():
    async def run():
        slots = LatestSlots()
        slots.put("a", b"a1")
        slots.put("b", b"b1")
        assert (await slots.get())[0] == "a"
        slots.put("a", b"a2")
        assert (await slots.get())[0] == "b"
        assert (await slots.get())[0] == "a"

    asyncio.run(run())


def test_get_waits_for_put():
    async def run():
        slots = LatestSlots()
        getter = asyncio.create_task(slots.get())
        await asyncio.sleep(0.01)
        assert not getter.done()
        slots.put("s", b"x")
        assert await asyncio.wait_for(getter, 1) == ("s", b"x")

    asyncio.run(run())
