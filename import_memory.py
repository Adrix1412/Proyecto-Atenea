"""Import old desktop exchanges into a new SQLite memory file."""

import argparse
from pathlib import Path

from alicia_core.adapters.sqlite_memory import SQLiteMemory
from alicia_core.errors import AliciaError
from alicia_desktop.config import load_config, resolve_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        destination = resolve_path(args.config, config.memory_path)
        if destination.resolve() == args.source.resolve():
            raise ValueError("El destino debe ser distinto del original.")
        count = SQLiteMemory(destination).import_legacy(args.source, args.dry_run)
        print(f"{count} mensajes {'validados' if args.dry_run else 'importados'}.")
        return 0
    except (AliciaError, ValueError, OSError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
