"""
Ramp event rate through tiers and print a results table.
Usage: python load_testing/benchmark_runner.py
"""
import asyncio
from load_testing.generate_events import send_events

TIERS = [
    {"rate": 500,   "duration": 20},
    {"rate": 1000,  "duration": 20},
    {"rate": 2000,  "duration": 20},
    {"rate": 5000,  "duration": 20},
    {"rate": 10000, "duration": 20},
]


async def main() -> None:
    print(f"{'Rate (e/s)':<12} {'Duration':<10} {'Sent':<10} {'Errors':<10} {'Error%':<8}")
    print("-" * 55)
    for tier in TIERS:
        result = await send_events(tier["rate"], tier["duration"], "http://localhost:8000")
        total = result["sent"] + result["errors"]
        error_pct = 100 * result["errors"] / max(total, 1)
        print(
            f"{tier['rate']:<12} {tier['duration']}s{'':<7} "
            f"{result['sent']:<10} {result['errors']:<10} {error_pct:.1f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())
