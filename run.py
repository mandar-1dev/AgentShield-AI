"""Start the AgentShield AI backend: python run.py"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("AGENTSHIELD_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENTSHIELD_PORT", "8000")),
    )
