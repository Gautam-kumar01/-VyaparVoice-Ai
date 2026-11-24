import sys
import os

# Add backend directory to sys.path so modules can import database, agent_engine, etc.
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app

# Vercel looks for the WSGI application callable named 'app'
if __name__ == "__main__":
    app.run()
