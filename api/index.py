import sys
import os
import urllib.parse

# Add backend directory to sys.path so modules can import database, agent_engine, etc.
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app

class VercelPathFixMiddleware:
    """
    WSGI middleware to fix PATH_INFO and QUERY_STRING when deployed on Vercel.
    Extracts the true path from __route__ query parameter passed by vercel.json rewrite.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        query_string = environ.get("QUERY_STRING", "")
        if "__route__" in query_string:
            params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
            if "__route__" in params:
                route_path = params.pop("__route__")[0]
                if route_path and route_path.startswith("/"):
                    environ["PATH_INFO"] = route_path
                # Rebuild remaining query string without __route__
                clean_pairs = []
                for k, vals in params.items():
                    for v in vals:
                        clean_pairs.append((k, v))
                environ["QUERY_STRING"] = urllib.parse.urlencode(clean_pairs)

        return self.wsgi_app(environ, start_response)

# Apply WSGI middleware
app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

# Vercel looks for the WSGI application callable named 'app'
if __name__ == "__main__":
    app.run()
