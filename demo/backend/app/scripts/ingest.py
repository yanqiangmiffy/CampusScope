"""Build (or check) the demo's Milvus collections from data/.

    docker compose exec backend python -m app.scripts.ingest              # build what is missing
    docker compose exec backend python -m app.scripts.ingest --recreate   # rebuild everything

The API does the same at start-up (INGEST_ON_START); use this after the data or the embedder changed.
"""
import argparse
import json

from app import system  # noqa: F401
from app.services import index_service, retrieval


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recreate", action="store_true", help="drop and rebuild every collection")
    args = ap.parse_args()
    retrieval.install()
    index_service.wait_for_milvus()
    print(json.dumps(index_service.ensure(recreate=args.recreate), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
