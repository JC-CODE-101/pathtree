import argparse
import sys

from pathtree.database.connection import get_session
from pathtree.database.repository import NodeRepository
from pathtree.services.seed import seed_development_data


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
    parser.add_argument(
        "--seed-dev",
        action="store_true",
        help="Idempotently seed development data into the database.",
    )

    args = parser.parse_args()

    if args.seed_dev:
        with get_session() as session:
            repository = NodeRepository(session)
            seed_development_data(repository)
        print("Development seed data populated successfully.")
        sys.exit(0)

    if args.output:
        print(f"PathTree CLI invoked. Output path registered: {args.output}")
    else:
        print("PathTree CLI invoked.")

    sys.exit(0)


if __name__ == "__main__":
    main()
