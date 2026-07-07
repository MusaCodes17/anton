"""
Run script for the Running Shoe Deal Finder API
Run this from the backend directory: python run.py
"""
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Default to loopback-only (R2.1): "localhost only" is now an app property,
    # not an accident of the network. Set API_HOST=0.0.0.0 to serve the LAN —
    # safe now that the bearer token (ANTON_SECRET) is required on every request.
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", 8000))
    
    print(f"""
    🏃‍♂️ Running Shoe Deal Finder API
    ================================
    Starting server at http://{host}:{port}
    API Documentation: http://localhost:{port}/docs
    Alternative Docs: http://localhost:{port}/redoc
    
    Press Ctrl+C to stop the server
    """)
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True  # Enable hot reload for development
    )
