import argparse
import sys


def main() -> None:
    """CLI entry point for PathTree."""
    parser = argparse.ArgumentParser(
        description="PathTree: Modern terminal workspace and path manager."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Path to a temporary file where selected directory path will be written.",
    )

    args = parser.parse_args()

    if args.output:
        print(f"PathTree CLI invoked. Output path registered: {args.output}")
    else:
        print("PathTree CLI invoked.")

    sys.exit(0)


if __name__ == "__main__":
    main()
