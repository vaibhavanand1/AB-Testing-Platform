import argparse
from concurrent.futures import ThreadPoolExecutor
import random
import statistics
import sys
import time
import httpx


def parse_args():
    parser = argparse.ArgumentParser(
        description="A/B Testing Platform Load Test & Latency Benchmarking Script"
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--users", type=int, default=5000, help="Number of simulated users")
    parser.add_argument(
        "--control-cvr", type=float, default=0.10, help="True control conversion rate (e.g. 0.10)"
    )
    parser.add_argument(
        "--treatment-cvr",
        type=float,
        default=0.13,
        help="True treatment conversion rate (e.g. 0.13)",
    )
    parser.add_argument(
        "--name", default="Checkout Flow Redesign", help="Experiment name to create/use"
    )
    parser.add_argument(
        "--concurrency", type=int, default=20, help="Concurrent workers for traffic generation"
    )
    parser.add_argument(
        "--benchmark-n",
        type=int,
        default=200,
        help="Sample size for latency comparison benchmark",
    )
    return parser.parse_args()


def get_or_create_experiment(client: httpx.Client, base_url: str, name: str) -> dict:
    resp = client.get(f"{base_url}/experiments")
    if resp.status_code == 200:
        for exp in resp.json():
            if exp["name"] == name:
                print(f"Using existing experiment '{name}' (ID: {exp['id']})")
                return exp

    payload = {
        "name": name,
        "variants": [
            {"name": "control", "weight": 50},
            {"name": "treatment", "weight": 50},
        ],
    }
    resp = client.post(f"{base_url}/experiments", json=payload)
    if resp.status_code in (200, 201):
        exp = resp.json()
        print(f"Created experiment '{name}' (ID: {exp['id']})")
        return exp
    else:
        print(f"Failed to create experiment: {resp.status_code} {resp.text}")
        sys.exit(1)


def benchmark_latency(client: httpx.Client, base_url: str, exp_id: int, sample_size: int):
    print("\n" + "=" * 60)
    print("LATENCY BENCHMARK: Cold (DB Fallback) vs Warm (Redis Cache)")
    print("=" * 60)

    # 1. Cold requests: new unique user IDs (forcing hash computation + DB insert)
    cold_latencies_ms = []
    benchmark_users = [f"bench_user_{i}_{int(time.time())}" for i in range(sample_size)]

    for uid in benchmark_users:
        t0 = time.perf_counter()
        resp = client.get(f"{base_url}/assign", params={"experiment_id": exp_id, "user_id": uid})
        t1 = time.perf_counter()
        if resp.status_code == 200:
            cold_latencies_ms.append((t1 - t0) * 1000)

    # 2. Warm requests: re-querying the same user IDs (served directly from Redis cache)
    warm_latencies_ms = []
    for uid in benchmark_users:
        t0 = time.perf_counter()
        resp = client.get(f"{base_url}/assign", params={"experiment_id": exp_id, "user_id": uid})
        t1 = time.perf_counter()
        if resp.status_code == 200:
            warm_latencies_ms.append((t1 - t0) * 1000)

    def stats_summary(data):
        if not data:
            return 0, 0, 0, 0
        sorted_data = sorted(data)
        p50 = statistics.median(sorted_data)
        p95 = sorted_data[int(len(sorted_data) * 0.95)]
        p99 = sorted_data[int(len(sorted_data) * 0.99)]
        mean = statistics.mean(sorted_data)
        return mean, p50, p95, p99

    c_mean, c_p50, c_p95, c_p99 = stats_summary(cold_latencies_ms)
    w_mean, w_p50, w_p95, w_p99 = stats_summary(warm_latencies_ms)

    print(f"Sample Size: {sample_size} requests per condition")
    print(f"{'Metric':<10} | {'Cold / DB (ms)':<16} | {'Warm / Redis (ms)':<16} | {'Speedup':<10}")
    print("-" * 60)
    speedup_mean = f"{c_mean / w_mean:.2f}x" if w_mean > 0 else "N/A"
    speedup_p50 = f"{c_p50 / w_p50:.2f}x" if w_p50 > 0 else "N/A"
    speedup_p95 = f"{c_p95 / w_p95:.2f}x" if w_p95 > 0 else "N/A"
    speedup_p99 = f"{c_p99 / w_p99:.2f}x" if w_p99 > 0 else "N/A"

    print(f"{'Mean':<10} | {c_mean:>14.2f} ms | {w_mean:>14.2f} ms | {speedup_mean:>8}")
    print(f"{'p50':<10} | {c_p50:>14.2f} ms | {w_p50:>14.2f} ms | {speedup_p50:>8}")
    print(f"{'p95':<10} | {c_p95:>14.2f} ms | {w_p95:>14.2f} ms | {speedup_p95:>8}")
    print(f"{'p99':<10} | {c_p99:>14.2f} ms | {w_p99:>14.2f} ms | {speedup_p99:>8}")
    print("=" * 60)


def simulate_user(args_tuple):
    base_url, exp_id, uid, control_cvr, treatment_cvr = args_tuple
    with httpx.Client(timeout=10.0) as client:
        # Step 1: Assign variant
        assign_resp = client.get(
            f"{base_url}/assign",
            params={"experiment_id": exp_id, "user_id": uid},
        )
        if assign_resp.status_code != 200:
            return None, False

        data = assign_resp.json()
        variant = data["variant"]

        # Step 2: Determine conversion based on true rate
        target_cvr = treatment_cvr if variant == "treatment" else control_cvr
        did_convert = random.random() < target_cvr

        # Step 3: Track conversion event if converted
        if did_convert:
            event_resp = client.post(
                f"{base_url}/events",
                json={
                    "experiment_id": exp_id,
                    "user_id": uid,
                    "variant": variant,
                    "event_type": "conversion",
                },
            )
            return variant, (event_resp.status_code in (200, 201))

        return variant, False


def run_traffic_simulation(
    base_url: str,
    exp_id: int,
    n_users: int,
    control_cvr: float,
    treatment_cvr: float,
    concurrency: int,
):
    print(f"\nSimulating {n_users:,} users with {concurrency} worker threads...")
    print(f"Target True CVR: Control = {control_cvr * 100:.1f}%, Treatment = {treatment_cvr * 100:.1f}%")

    prefix = f"sim_{int(time.time())}"
    tasks = [
        (base_url, exp_id, f"{prefix}_{i}", control_cvr, treatment_cvr)
        for i in range(n_users)
    ]

    t0 = time.time()
    completed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in executor.map(simulate_user, tasks):
            completed += 1
            if completed % max(1, n_users // 10) == 0 or completed == n_users:
                elapsed = time.time() - t0
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"Progress: {completed:,}/{n_users:,} users ({completed/n_users*100:.0f}%) - {rate:.1f} req/s")

    duration = time.time() - t0
    print(f"Simulation completed in {duration:.2f}s ({n_users / duration:.1f} users/sec).")


def print_experiment_results(client: httpx.Client, base_url: str, exp_id: int):
    resp = client.get(f"{base_url}/experiments/{exp_id}/results")
    if resp.status_code != 200:
        print(f"Failed to fetch results: {resp.status_code}")
        return

    data = resp.json()
    print("\n" + "=" * 70)
    print(f"FINAL EXPERIMENT RESULTS: {data['experiment_name']} (ID: {data['experiment_id']})")
    print("=" * 70)

    print(f"{'Variant':<12} | {'Weight':<8} | {'Sample Size':<12} | {'Conversions':<12} | {'Conversion Rate':<16}")
    print("-" * 70)
    for v in data["variants"]:
        print(
            f"{v['name']:<12} | "
            f"{v['weight']:<8} | "
            f"{v['sample_size']:<12,d} | "
            f"{v['conversions']:<12,d} | "
            f"{v['conversion_rate_percentage']:>6.2f}%"
        )

    print("-" * 70)
    print("STATISTICAL INFERENCE (Two-sample proportion Z-test):")
    for comp in data.get("comparisons", []):
        ci = comp["confidence_interval"]
        print(f"Comparison: {comp['treatment_variant']} vs {comp['control_variant']}")
        print(f"  - Absolute Difference:   {comp['absolute_diff'] * 100:+.2f}%")
        print(f"  - Relative Lift:         {comp['relative_lift_percentage']:+.2f}%")
        print(f"  - Z-Statistic:           {comp['z_score']}")
        print(f"  - P-Value:               {comp['p_value']:.5f}")
        print(f"  - 95% Conf. Interval:    [{ci[0] * 100:+.2f}%, {ci[1] * 100:+.2f}%]")
        print(f"  - Peeking Guard Active:  {comp['peeking_guard_active']}")
        print(f"  - Statistically Signif:  {comp['is_significant']}")
        print(f"  - Conclusion:            {comp['message']}")
    print("=" * 70)


def main():
    args = parse_args()
    with httpx.Client(timeout=15.0) as client:
        # 1. Health check
        try:
            health = client.get(f"{args.base_url}/health")
            if health.status_code != 200:
                print(f"API health check failed: {health.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Could not connect to API at {args.base_url}: {e}")
            print("Please ensure the FastAPI backend is running.")
            sys.exit(1)

        # 2. Experiment setup
        exp = get_or_create_experiment(client, args.base_url, args.name)
        exp_id = exp["id"]

        # 3. Latency benchmark
        benchmark_latency(client, args.base_url, exp_id, args.benchmark_n)

        # 4. Traffic simulation
        run_traffic_simulation(
            args.base_url,
            exp_id,
            args.users,
            args.control_cvr,
            args.treatment_cvr,
            args.concurrency,
        )

        # 5. Results & stats verification
        print_experiment_results(client, args.base_url, exp_id)


if __name__ == "__main__":
    main()
