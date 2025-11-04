"""Script para executar o servidor em modo desenvolvimento com hot-reload."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Habilita hot-reload
        reload_dirs=["./api", "./static", "./templates"],  # Diretórios para monitorar
        reload_includes=["*.py", "*.html", "*.css", "*.js"],  # Tipos de arquivo para monitorar
        log_level="info",
    )
