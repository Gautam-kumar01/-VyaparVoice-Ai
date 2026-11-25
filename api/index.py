import sys
import os

# Add backend directory to sys.path so modules can import database, agent_engine, etc.
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app

class VercelPathFixMiddleware:
    """
    WSGI middleware to fix PATH_INFO and QUERY_STRING when deployed on Vercel.
    When Vercel rewrites requests from /api/(.*) to /api/index.py, WSGI PATH_INFO
    is often set to '/api/index.py' or '/index.py' instead of the true requested path.
    This middleware extracts the true path from REQUEST_URI / RAW_URI / HTTP_X_MATCHED_PATH.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        # If PATH_INFO is pointing to the handler script itself
        if (
            not path_info or 
            path_info in ("/api/index.py", "/api/index", "/index.py", "/api/", "/api", "") or
            path_info.endswith("/index.py")
        ):
            candidate = (
                environ.get("REQUEST_URI") or
                environ.get("RAW_URI") or
                environ.get("HTTP_X_MATCHED_PATH") or
                environ.get("HTTP_X_FORWARDED_URI") or
                ""
            )
            if candidate:
                if "?" in candidate:
                    parts = candidate.split("?", 1)
                    clean_path = parts[0]
                    if len(parts) > 1 and not environ.get("QUERY_STRING"):
                        environ["QUERY_STRING"] = parts[1]
                else:
                    clean_path = candidate

                if clean_path.startswith("/"):
                    environ["PATH_INFO"] = clean_path

        return self.wsgi_app(environ, start_response)

# Apply WSGI middleware
app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

# Vercel looks for the WSGI application callable named 'app'
if __name__ == "__main__":
    app.run()
