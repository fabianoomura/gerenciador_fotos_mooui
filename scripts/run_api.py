"""Inicia a API local do catálogo."""

import os

import uvicorn

from catalogo.api import create_app

if __name__ == "__main__":
    host = os.environ.get("CATALOGO_HOST", "127.0.0.1")
    port = int(os.environ.get("CATALOGO_PORT", "8000"))
    db_path = os.environ.get("CATALOGO_DB", "catalogo.db")
    api_token = os.environ.get("CATALOGO_API_TOKEN")
    if not api_token and os.environ.get("CATALOGO_ALLOW_UNAUTHENTICATED") != "1":
        raise RuntimeError(
            "Defina CATALOGO_API_TOKEN ou, apenas em desenvolvimento local, "
            "CATALOGO_ALLOW_UNAUTHENTICATED=1"
        )
    cors_origins = [
        origin.strip()
        for origin in os.environ.get("CATALOGO_CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    uvicorn.run(
        create_app(db_path=db_path, cors_origins=cors_origins, api_token=api_token),
        host=host,
        port=port,
    )
