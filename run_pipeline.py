import subprocess
import sys
import os


def run_step(name, script):
    print(f"\n{'='*60}")
    print(f"  Running: {name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True, cwd=os.path.dirname(__file__) or ".")
    if result.returncode != 0:
        print(f"[ERROR] {name} failed:\n{result.stderr}")
        return False
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    return True


def main():
    steps = [
        ("Mock Operational Tables", "mock_operations.py"),
        ("Customer Segmentation (K-Means)", "customer_segmentation.py"),
    ]
    success = True
    for name, script in steps:
        if not run_step(name, script):
            success = False
            break
    if success:
        print(f"\nPipeline completed successfully.")
    else:
        print(f"\nPipeline failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
