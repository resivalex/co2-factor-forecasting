"""Run the whole pipeline: `python -m co2_forecast`."""

from co2_forecast import evaluate, fetch, forecast, train


def main() -> None:
    for step in (fetch, train, evaluate, forecast):
        step.main()


if __name__ == "__main__":
    main()
