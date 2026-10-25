"""`python -m orbit` starts the API on localhost only (never 0.0.0.0)."""

import uvicorn


def main() -> None:
    uvicorn.run("orbit.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
