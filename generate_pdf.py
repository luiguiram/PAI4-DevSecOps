#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
GENERADOR DE INFORME PDF OFICIAL - PAI 4 (DEVSECOPS)
Módulo: generate_pdf.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet - PAI 4
Convocatoria: Curso Académico 2026 / 2027
Universidad de Sevilla - E.T.S. Ingeniería Informática
========================================================================================
"""

import os
import sys
import re
import shutil
import subprocess
from pathlib import Path
import markdown

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(BASE_DIR, "INFORME-PAI4-ST3.md")
PDF_PATH = os.path.join(BASE_DIR, "INFORME-PAI4-ST3.pdf")
HTML_TEMP = os.path.join(BASE_DIR, "informe_temp.html")


def find_chromium_browser():
    """Detecta un navegador compatible con Chromium (Brave, Chrome, Chromium o Edge) en Linux, Windows o macOS."""
    override = os.environ.get("PDF_BROWSER")
    if override and (shutil.which(override) or os.path.isfile(override)):
        return override

    for binary in ("brave", "brave-browser", "google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(binary)
        if found:
            return found

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidate_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.join(local_app_data, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in candidate_paths:
        if path and os.path.isfile(path):
            return path

    return None

def convert_markdown_to_pdf():
    if not os.path.exists(MD_PATH):
        print(f"[!] Error: No se encontró el archivo Markdown en {MD_PATH}")
        sys.exit(1)

    with open(MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    def render_callout(css_class, title, raw_md):
        inner = markdown.markdown(raw_md.replace('> ', ''), extensions=["extra"])
        return f'<div class="callout {css_class}"><strong>{title}</strong>{inner}</div>\n'

    # Sustitución de callouts de GitHub por bloques estilizados
    text = re.sub(
        r'> \[!IMPORTANT\]\n((?:> .*\n?)+)',
        lambda m: render_callout('callout-important', 'AVISO DE SEGURIDAD CRÍTICO:', m.group(1)),
        text
    )
    text = re.sub(
        r'> \[!NOTE\]\n((?:> .*\n?)+)',
        lambda m: render_callout('callout-note', 'NOTA TÉCNICA:', m.group(1)),
        text
    )
    text = re.sub(
        r'> \[!WARNING\]\n((?:> .*\n?)+)',
        lambda m: render_callout('callout-warning', 'ADVERTENCIA DEVSECOPS:', m.group(1)),
        text
    )
    text = re.sub(
        r'> \[!TIP\]\n((?:> .*\n?)+)',
        lambda m: render_callout('callout-tip', 'RECOMENDACIÓN TÉCNICA:', m.group(1)),
        text
    )

    body_html = markdown.markdown(text, extensions=["tables", "fenced_code", "extra", "sane_lists"])

    # Conversión de rutas relativas de imágenes a URIs absolutos (compatible con Linux/Windows/macOS)
    evidencias_uri = Path(BASE_DIR, "evidencias").as_uri()
    body_html = body_html.replace('src="evidencias/', f'src="{evidencias_uri}/')
    body_html = body_html.replace('src="./evidencias/', f'src="{evidencias_uri}/')

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>INFORME-PAI4-ST3 - Auditoría e Implementación DevSecOps</title>
<style>
  @page {{
    size: A4;
    margin: 14mm 14mm 14mm 14mm;
    @bottom-right {{
      content: "Página " counter(page);
      font-size: 8pt;
      color: #64748b;
    }}
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #1e293b;
    line-height: 1.42;
    font-size: 8.9pt;
  }}
  h1 {{
    font-size: 15.5pt;
    color: #0f172a;
    border-bottom: 2px solid #0284c7;
    padding-bottom: 4px;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
  }}
  h2 {{
    font-size: 12.2pt;
    color: #0369a1;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 3px;
    margin-top: 12px;
    margin-bottom: 5px;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 10.2pt;
    color: #0284c7;
    margin-top: 10px;
    margin-bottom: 4px;
    page-break-after: avoid;
  }}
  h4 {{
    font-size: 9.4pt;
    color: #334155;
    margin-top: 8px;
    margin-bottom: 2px;
    page-break-after: avoid;
  }}
  p, ul, ol {{
    margin-top: 3px;
    margin-bottom: 4px;
  }}
  li {{
    margin-bottom: 2px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 6px 0;
    font-size: 8.0pt;
    page-break-inside: avoid;
  }}
  th, td {{
    border: 1px solid #cbd5e1;
    padding: 3.5px 5.5px;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
  }}
  tr:nth-child(even) td {{
    background-color: #f8fafc;
  }}
  code {{
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 8.0pt;
    background-color: #f1f5f9;
    padding: 1px 3px;
    border-radius: 3px;
    color: #0369a1;
  }}
  pre {{
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #0284c7;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 7.4pt;
    line-height: 1.25;
    overflow-x: auto;
    margin: 4px 0;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  pre code {{
    background: none;
    padding: 0;
    color: #1e293b;
    font-size: 7.4pt;
  }}
  img {{
    display: block;
    max-width: 98%;
    height: auto;
    margin: 8px auto;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    page-break-inside: avoid;
  }}
  .callout {{
    padding: 6px 10px;
    margin: 5px 0;
    border-radius: 4px;
    font-size: 8.3pt;
    page-break-inside: avoid;
  }}
  .callout-important {{
    background-color: #eff6ff;
    border-left: 4px solid #3b82f6;
    color: #1e3a8a;
  }}
  .callout-note {{
    background-color: #f0fdf4;
    border-left: 4px solid #22c55e;
    color: #14532d;
  }}
  .callout-warning {{
    background-color: #fffbeb;
    border-left: 4px solid #f59e0b;
    color: #78350f;
  }}
  .callout-tip {{
    background-color: #faf5ff;
    border-left: 4px solid #a855f7;
    color: #581c87;
  }}
  blockquote {{
    border-left: 3px solid #94a3b8;
    margin: 4px 0;
    padding-left: 8px;
    color: #475569;
    font-style: italic;
  }}
  hr {{
    border: 0;
    border-top: 1px solid #e2e8f0;
    margin: 8px 0;
  }}
  .page-break {{
    page-break-before: always;
  }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

    browser = find_chromium_browser()
    if not browser:
        print("[!] Error: No se encontró un navegador compatible (Brave, Chrome, Chromium o Edge).")
        print("    Instale alguno o indique la ruta en la variable de entorno PDF_BROWSER.")
        sys.exit(1)

    with open(HTML_TEMP, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[*] Compilando PDF mediante navegador headless ({os.path.basename(browser)})...")
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        Path(HTML_TEMP).as_uri()
    ]
    try:
        subprocess.run(cmd, check=True)
    finally:
        if os.path.exists(HTML_TEMP):
            os.remove(HTML_TEMP)

    if os.path.exists(PDF_PATH):
        size_kb = os.path.getsize(PDF_PATH) / 1024
        try:
            pdfinfo = subprocess.check_output(["pdfinfo", PDF_PATH], text=True)
            pages_match = re.search(r"Pages:\s+(\d+)", pdfinfo)
            pages = pages_match.group(1) if pages_match else "?"
            print(f"[OK] Documento PDF oficial generado exitosamente: {PDF_PATH}")
            print(f"     Páginas totales: {pages} (Límite normativo: máx. 15 páginas sin portada ni anexos) | Tamaño: {size_kb:.1f} KB")
        except Exception:
            print(f"[OK] Documento PDF oficial generado exitosamente: {PDF_PATH} | Tamaño: {size_kb:.1f} KB")

if __name__ == "__main__":
    convert_markdown_to_pdf()
