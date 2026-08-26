"""Runs the web UI: builds the frontend, then serves it + the API on one port.

This is the one-command way to see the UI - no manual npm commands needed
(Node/npm still needs to be installed, since the frontend is TypeScript, but
this script drives it). For active frontend development (hot-reload on
save), run the Vite dev server instead (`npm run dev` inside web/).
"""

import pathlib
import subprocess

import uvicorn

WEB_DIR = pathlib.Path(__file__).parent / "web"


def build_frontend() -> None:
    if not (WEB_DIR / "node_modules").exists():
        print("Installing frontend dependencies (first run only)...")
        subprocess.run(["npm", "install"], cwd=WEB_DIR, check=True)

    print("Building frontend...")
    subprocess.run(["npm", "run", "build"], cwd=WEB_DIR, check=True)


if __name__ == "__main__":
    build_frontend()
    print("Invoice Agent Pipeline running at http://localhost:8000")
    uvicorn.run("api:app", host="127.0.0.1", port=8000)
