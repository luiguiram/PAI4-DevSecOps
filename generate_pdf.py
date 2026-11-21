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
    margin: 11mm 12.5mm 12mm 12.5mm;
    @bottom-right {{
      content: "Página " counter(page);
      font-size: 8pt;
      color: #64748b;
    }}
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #1e293b;
    line-height: 1.34;
    font-size: 8.65pt;
  }}
  a {{
    color: #0369a1;
    text-decoration: underline;
    text-decoration-color: #bae6fd;
    text-underline-offset: 2px;
  }}
  h1 {{
    font-size: 15pt;
    color: #0f172a;
    border-bottom: 2px solid #0284c7;
    padding-bottom: 4px;
    margin-top: 10px;
    margin-bottom: 6px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  h2 {{
    font-size: 11.8pt;
    color: #0369a1;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 2px;
    margin-top: 10px;
    margin-bottom: 4px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 9.8pt;
    color: #0284c7;
    margin-top: 8px;
    margin-bottom: 3px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  h4 {{
    font-size: 9.2pt;
    color: #334155;
    margin-top: 6px;
    margin-bottom: 2px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  p, ul, ol {{
    margin-top: 2px;
    margin-bottom: 4px;
    orphans: 3;
    widows: 3;
  }}
  li {{
    margin-bottom: 2px;
    orphans: 2;
    widows: 2;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 5px 0;
    font-size: 7.9pt;
    page-break-inside: auto;
  }}
  thead {{
    display: table-header-group;
  }}
  tr {{
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  th, td {{
    border: 1px solid #cbd5e1;
    padding: 3px 5px;
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
    font-size: 7.8pt;
    background-color: #f1f5f9;
    padding: 1px 3px;
    border-radius: 3px;
    color: #0369a1;
  }}
  pre {{
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #0284c7;
    padding: 4px 7px;
    border-radius: 4px;
    font-size: 7.2pt;
    line-height: 1.18;
    overflow-x: auto;
    margin: 4px 0;
    page-break-inside: avoid;
    break-inside: avoid;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    word-break: normal;
  }}
  pre code {{
    background: none;
    padding: 0;
    color: #1e293b;
    font-size: 7.2pt;
  }}
  img {{
    display: block;
    max-width: 96%;
    height: auto;
    margin: 6px auto;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  .callout {{
    padding: 5px 9px;
    margin: 5px 0;
    border-radius: 4px;
    font-size: 8.2pt;
    page-break-inside: avoid;
    break-inside: avoid;
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
    margin: 6px 0;
  }}
  .page-break {{
    page-break-before: always;
    break-before: page;
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
        pages = "?"
        try:
            pdfinfo = subprocess.check_output(["pdfinfo", PDF_PATH], text=True)
            pages_match = re.search(r"Pages:\s+(\d+)", pdfinfo)
            if pages_match:
                pages = pages_match.group(1)
        except Exception:
            try:
                with open(PDF_PATH, "rb") as pdf_file:
                    raw = pdf_file.read()
                count = len(re.findall(rb"/Type\s*/Page\b", raw))
                if count > 0:
                    pages = str(count)
            except Exception:
                pass
        print(f"[OK] Documento PDF oficial generado exitosamente: {PDF_PATH}")
        print(f"     Páginas totales: {pages} (Límite normativo: máx. 15 páginas sin portada, índice, referencias ni anexos) | Tamaño: {size_kb:.1f} KB")

if __name__ == "__main__":
    convert_markdown_to_pdf()
