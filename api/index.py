"""Vercel serverless entry point: exposes the FastAPI app from backend/app."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.environ.setdefault("SKYOPS_DB", "/tmp/skyops.db")

from app.main import app  # noqa: E402,F401
