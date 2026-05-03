"""Run a small demo report from the modular Vivi package."""

from vivi.demo import demo


if __name__ == "__main__":
    path = demo()
    print(f"Wrote demo report: {path}")
