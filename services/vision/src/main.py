import asyncio
import logging

from .pipeline import VisionPipeline

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    pipeline = VisionPipeline()
    await pipeline.start()


if __name__ == "__main__":
    asyncio.run(main())
