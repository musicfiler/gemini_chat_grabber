# gemini_crawler.py
# Version: 48.0 (Header Layout Fix: Vertical Align Bottom, Safe Margins)
import time
import json
import re
import html
import os
import hashlib
import requests
import traceback
import pathlib
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import markdownify
import markdown

try:
    import sys

    os.environ['G_MESSAGES_DEBUG'] = 'none'
    import logging

    logging.getLogger('weasyprint').setLevel(logging.ERROR)
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
except ImportError:
    print("Warnung: WeasyPrint konnte nicht geladen werden.")

from database_manager import DatabaseManager


class GeminiCrawlerProcess:
    def __init__(self, urls, log_queue, config_file="config.json",
                 export_mode="single", pdf_export=False, include_model_toc=False,
                 base_output_dir="output", index_only=False, duplex_mode=False,
                 detailed_index=True, save_raw=False, page_num_pos="bottom"):

        self.urls = urls
        self.queue = log_queue
        self.config_file = config_file
        self.export_mode = export_mode
        self.pdf_export = pdf_export
        self.include_model_toc = include_model_toc
        self.base_output_dir = base_output_dir
        self.index_only = index_only
        self.duplex_mode = duplex_mode
        self.detailed_index = detailed_index
        self.save_raw = save_raw
        self.page_num_pos = page_num_pos

        with open(config_file, "r") as f:
            self.config = json.load(f)

        if not self.index_only:
            self.dirs = self._prepare_output_dirs()
        else:
            self.dirs = {"assets": os.path.join(base_output_dir, "db_assets"), "base": base_output_dir}
            os.makedirs(self.dirs["assets"], exist_ok=True)

    def _prepare_output_dirs(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base = os.path.join(self.base_output_dir, f"crawl_{timestamp}")
        dirs = {
            "base": base,
            "raw": os.path.join(base, "raw_crawl_data"),
            "screens": os.path.join(base, "screenshots"),
            "assets": os.path.join(base, "crawl_data"),
            "json": os.path.join(base, "crawl_data", "json"),
            "pdfs": os.path.join(base, "pdfs") if self.pdf_export else base,
            "final": base
        }
        for d in dirs.values():
            if d != base or not os.path.exists(d): os.makedirs(d, exist_ok=True)
        return dirs

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.queue.put(f"[GEMINI {timestamp}] {msg}")

    def _sanitize_filename(self, text, index):
        clean = re.sub(r'[^a-zA-Z0-9äöüÄÖÜß]', '_', text)
        clean = re.sub(r'_+', '_', clean).strip('_')
        return f"{index + 1:02d}_{clean[:60]}"

    # --- HTML & HELPERS ---

    def _brute_force_sanitize(self, text_content):
        """
        Ersetzt problematische Strings direkt im Raw-Text, BEVOR irgendein Parser sie sieht.
        """
        if not text_content: return ""
        replacements = [
            ("<script", "[CODE:script"),
            ("</script>", "[/CODE:script]"),
            ("&lt;script", "[CODE:script"),
            ("&lt;/script", "[/CODE:script]"),
            ("<iframe", "[CODE:iframe"),
            ("</iframe>", "[/CODE:iframe]"),
            ("<object", "[CODE:object"),
            ("<embed", "[CODE:embed"),
        ]
        safe_text = str(text_content)
        for old, new in replacements:
            safe_text = safe_text.replace(old, new)
            safe_text = safe_text.replace(old.upper(), new)
        return safe_text

    def _get_toc_display_text(self, turn):
        snippet = turn['user'].strip()
        snippet = re.sub(r'!\[.*?\]\(.*?\)', '', snippet).strip()
        has_images = len(turn.get('images', [])) > 0
        if not snippet and has_images: return f"{turn['index']}. 📷 Dateiprompt"

        clean = re.sub(r'[*_`#\[\]]', '', snippet).strip()
        truncated = (clean[:50] + '...') if len(clean) > 50 else clean
        return f"{turn['index']}. {truncated}"

    def _get_short_header_text(self, text):
        c = re.sub(r'!\[.*?\]\(.*?\)', '', text).strip()
        c = re.sub(r'[*_`#\[\]]', '', c).strip()
        if not c: return "Bild/Datei"
        # Kürzerer Header Text für die Mitte (max 60 chars)
        return (c[:60] + '...') if len(c) > 60 else c

    def _render_markdown(self, t):
        try:
            return markdown.markdown(t, extensions=['fenced_code', 'tables', 'nl2br'])
        except:
            return f"<pre>{html.escape(t)}</pre>"

    def _get_img_src(self, img):
        s = img.get('src') or img.get('data-src')
        return s if s and s.startswith('http') and ('google' in s or 'generated' in s) and 'avatar' not in str(
            img.get('class')) else None

    def _download_single_image(self, url, headers):
        try:
            ext = "png" if "png" in url else "jpg"
            fn = f"img_{hashlib.md5(url.encode()).hexdigest()[:10]}.{ext}"
            fp = os.path.join(self.dirs['assets'], fn)
            if not os.path.exists(fp):
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    with open(fp, "wb") as f: f.write(r.content)
            return f"crawl_data/{fn}"
        except:
            return None

    def _process_and_download_images(self, chat):
        headers = {"User-Agent": "Mozilla/5.0"}
        for t in chat['turns']:
            t['images'] = [self._download_single_image(u, headers) for u in t['images'] if
                           self._download_single_image(u, headers)]
            for u in re.findall(r'\[IMG:(http[^\]]+)\]', t['model']):
                if p := self._download_single_image(u, headers):
                    t['model'] = t['model'].replace(f"[IMG:{u}]", f'<br><img src="{p}"><br>')

    # --- MAIN RUN ---
    def run(self):
        self.log(f"Start v48.0. Index={self.detailed_index}, Duplex={self.duplex_mode}, PagePos={self.page_num_pos}")
        db = DatabaseManager(self.config_file)
        chat_metadata_list = []

        with sync_playwright() as p:
            headless = not self.config.get("browser_visible", True)
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(user_agent=self.config.get("user_agent"))
            page = context.new_page()

            for i, url in enumerate(self.urls):
                if not url.strip(): continue
                self.log(f"Crawle ({i + 1}/{len(self.urls)}): {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000);
                    time.sleep(5)
                    try:
                        page.get_by_role("button", name=re.compile(r"(alle akzeptieren|accept all|zustimmen)",
                                                                   re.IGNORECASE)).first.click(
                            timeout=2000); time.sleep(2)
                    except:
                        pass
                    content = page.content()

                    if self.save_raw and not self.index_only:
                        try:
                            raw_fn = f"raw_{i}_{hashlib.md5(url.encode()).hexdigest()[:6]}.html"
                            with open(os.path.join(self.dirs['raw'], raw_fn), "w", encoding="utf-8") as f:
                                f.write(content)
                        except Exception as e:
                            self.log(f"Raw Save Error: {e}")

                    scr_path = ""
                    if not self.index_only:
                        temp_scr = os.path.join(self.dirs['screens'], f"temp_{i}.png")
                        page.screenshot(path=temp_scr, full_page=True);
                        scr_path = temp_scr

                    chat_data, status = self._extract_dom_data(content, url)

                    if chat_data:
                        self._process_and_download_images(chat_data)
                        base_name = self._sanitize_filename(chat_data['title'], i)
                        chat_data['id_number'] = i + 1

                        if not self.index_only and os.path.exists(scr_path):
                            final_scr = f"{base_name}_screen.png"
                            os.rename(scr_path, os.path.join(self.dirs['screens'], final_scr))
                            chat_data['screenshot_filename'] = final_scr
                            chat_data['screenshot_path_abs'] = os.path.abspath(
                                os.path.join(self.dirs['screens'], final_scr))

                        html_preview = self._render_template_browser([chat_data], start_index=i)
                        db.save_content(url, chat_data['title'], html_preview, chat_data, "GeminiV48")

                        if self.index_only:
                            self.log(f" -> Nur Indiziert: {chat_data['title']}")
                            continue

                        chat_data['filename'] = f"{base_name}.html"
                        json_path = os.path.join(self.dirs['json'], f"{base_name}.json")
                        with open(json_path, "w", encoding="utf-8") as jf:
                            json.dump(chat_data, jf, indent=4)

                        meta = {
                            "title": chat_data['title'], "id_number": i + 1, "filename": chat_data['filename'],
                            "json_path": json_path, "original_date": chat_data['original_date'],
                            "publish_date": chat_data['publish_date'], "model": chat_data['model'],
                            "url": chat_data['url'], "screenshot_filename": chat_data.get('screenshot_filename', '')
                        }
                        chat_metadata_list.append(meta)

                        if self.export_mode in ["single", "all"]:
                            with open(os.path.join(self.dirs['final'], chat_data['filename']), "w",
                                      encoding="utf-8") as f:
                                f.write(html_preview)
                            if self.pdf_export:
                                self._generate_book_pdf_single(chat_data,
                                                               os.path.join(self.dirs['pdfs'], f"{base_name}.pdf"))
                        self.log(f" -> Verarbeitet: {chat_data['title']}")
                    else:
                        self.log(f" -> Skip: {status}")
                except Exception as e:
                    self.log(f"Fehler bei {url}: {e}"); traceback.print_exc()
            browser.close()

        if self.index_only: self.log("Fertig."); return

        if self.export_mode in ["single", "all"] and chat_metadata_list: self._create_index_file(chat_metadata_list)
        if self.export_mode in ["merged", "all"] and chat_metadata_list:
            self.log(f"Erstelle Zusammenfassung...")
            base_merged = f"KI-Verzeichnis_{datetime.now().strftime('%Y-%m-%d')}"
            self._create_merged_file_from_json(chat_metadata_list,
                                               os.path.join(self.dirs['final'], f"{base_merged}.html"))
            if self.pdf_export:
                self.log("Erstelle Merged PDF...")
                self._generate_book_pdf_merged_from_json(chat_metadata_list,
                                                         os.path.join(self.dirs['pdfs'], f"{base_merged}.pdf"))
        self.log("Fertig.")

    def run_export_from_db(self, chat_data_list, custom_title="KI-Zusammenstellung"):
        self.log(f"Starte DB Export ({len(chat_data_list)} Objekte)...")
        self.dirs = self._prepare_output_dirs()
        chat_metadata_list = []
        for i, chat in enumerate(chat_data_list):
            base_name = self._sanitize_filename(chat['title'], i)
            chat['id_number'] = i + 1
            chat['filename'] = f"{base_name}.html"
            json_path = os.path.join(self.dirs['json'], f"{base_name}.json")
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(chat, jf, indent=4)
            meta = {
                "title": chat['title'], "id_number": i + 1, "filename": chat['filename'], "json_path": json_path,
                "original_date": chat.get('original_date', ''), "publish_date": chat.get('publish_date', ''),
                "model": chat.get('model', 'Gemini'), "url": chat.get('url', ''), "screenshot_filename": ""
            }
            chat_metadata_list.append(meta)
            try:
                html_out = self._render_template_browser([chat], start_index=i)
                with open(os.path.join(self.dirs['final'], chat['filename']), "w", encoding="utf-8") as f:
                    f.write(html_out)
                if self.pdf_export:
                    self._generate_book_pdf_single(chat, os.path.join(self.dirs['pdfs'], f"{base_name}.pdf"))
            except Exception as e:
                self.log(f"Fehler bei Export Item {i}: {e}")

        if len(chat_metadata_list) > 0:
            merged_name = self._sanitize_filename(custom_title, 0)
            self._create_merged_file_from_json(chat_metadata_list,
                                               os.path.join(self.dirs['final'], f"{merged_name}.html"))
            if self.pdf_export:
                self._generate_book_pdf_merged_from_json(chat_metadata_list,
                                                         os.path.join(self.dirs['pdfs'], f"{merged_name}.pdf"))
        self.log("DB Export Fertig.")

    # --- PDF CSS (FIXED MARGINS & ALIGNMENT) ---
    def _get_common_pdf_css(self):
        page_num = "counter(page)"
        doc_title = '"KI-Dokumentation"'

        if self.page_num_pos == "top":
            left_tl = page_num;
            left_tr = "string(chat_title)"
            right_tl = "string(chat_title)";
            right_tr = page_num
            footer_center = doc_title;
            footer_side = "none"
        else:  # Bottom (Standard)
            left_tl = "string(turn_num)";
            left_tr = "string(chat_title)"
            right_tl = "string(chat_title)";
            right_tr = "string(turn_num)"
            footer_center = doc_title;
            footer_side = page_num

        # Simplex logic
        simp_tl = "string(chat_title)";
        simp_tr = "string(turn_num)"

        # 3cm TOP Margin to avoid sticky headers
        # Vertical Align BOTTOM ensures text sits near the body, away from edge
        # Padding Bottom creates gap between Header and Body

        css_duplex = f"""
        @page:left {{
            margin: 30mm 20mm 25mm 25mm;

            @top-left {{ content: {left_tl}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; vertical-align: bottom; padding-bottom: 5mm; width: 20%; overflow:hidden; }}
            @top-center {{ content: string(turn_title); font-size: 8pt; color: #777; font-family: 'Segoe UI'; width: 60%; text-align: center; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; vertical-align: bottom; padding-bottom: 5mm; }}
            @top-right {{ content: {left_tr}; width: 20%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 9pt; color: #555; font-family: 'Segoe UI'; text-align:right; font-weight:bold; vertical-align: bottom; padding-bottom: 5mm; }}

            @bottom-left {{ content: {footer_side if self.page_num_pos == 'bottom' else 'none'}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; vertical-align: top; padding-top: 5mm; }}
            @bottom-center {{ content: {footer_center}; font-size: 8pt; color: #aaa; font-family: 'Segoe UI'; vertical-align: top; padding-top: 5mm; }}
            @bottom-right {{ content: none; }}
        }}
        @page:right {{
            margin: 30mm 25mm 25mm 20mm;

            @top-left {{ content: {right_tl}; width: 20%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 9pt; color: #555; font-family: 'Segoe UI'; font-weight:bold; vertical-align: bottom; padding-bottom: 5mm; }}
            @top-center {{ content: string(turn_title); font-size: 8pt; color: #777; font-family: 'Segoe UI'; width: 60%; text-align: center; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; vertical-align: bottom; padding-bottom: 5mm; }}
            @top-right {{ content: {right_tr}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; width: 20%; text-align: right; vertical-align: bottom; padding-bottom: 5mm; }}

            @bottom-left {{ content: none; }}
            @bottom-center {{ content: {footer_center}; font-size: 8pt; color: #aaa; font-family: 'Segoe UI'; vertical-align: top; padding-top: 5mm; }}
            @bottom-right {{ content: {footer_side if self.page_num_pos == 'bottom' else 'none'}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; vertical-align: top; padding-top: 5mm; }}
        }}
        """

        css_simplex = f"""
        @page {{
            size: A4; margin: 30mm 20mm 25mm 20mm;

            @top-left {{ content: {simp_tl}; width: 20%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 9pt; color: #555; font-family: 'Segoe UI'; font-weight:bold; vertical-align: bottom; padding-bottom: 5mm; }}
            @top-center {{ content: string(turn_title); font-size: 8pt; color: #777; font-family: 'Segoe UI'; width: 60%; text-align: center; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; vertical-align: bottom; padding-bottom: 5mm; }}
            @top-right {{ content: {simp_tr}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; width: 20%; text-align: right; vertical-align: bottom; padding-bottom: 5mm; }}

            @bottom-center {{ content: {doc_title}; font-size: 8pt; color: #aaa; font-family: 'Segoe UI'; margin-right: 20px; vertical-align: top; padding-top: 5mm; }}
            @bottom-right {{ content: {page_num if self.page_num_pos == 'bottom' else 'none'}; font-size: 10pt; font-family: 'Segoe UI'; font-weight:bold; vertical-align: top; padding-top: 5mm; }}
        }}
        """

        layout = css_duplex if self.duplex_mode else css_simplex

        return layout + """
        @page :first { @top-left { content: none; } @top-center { content: none; } @top-right { content: none; } @bottom-left { content: none; } @bottom-center { content: none; } @bottom-right { content: none; } }
        body { font-family: 'Segoe UI', sans-serif; font-size: 11pt; line-height: 1.5; color: #333; }

        h1 { color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; margin-top: 0; string-set: chat_title content(); }
        .toc-header-marker { string-set: chat_title "Inhaltsverzeichnis", turn_title "", turn_num ""; }
        .legend-header { string-set: chat_title "Legende & Hinweise", turn_title "", turn_num ""; }
        .turn-header-marker { string-set: turn_title attr(data-title), turn_num attr(data-num); }

        h2 { font-size: 14pt; margin-top: 20px; color: #444; border-bottom: 1px solid #eee; }
        .title-screenshot { display: block; margin: 20px auto; max-width: 95%; max-height: 11cm; object-fit: contain; border: 1px solid #ccc; box-shadow: 2px 2px 8px rgba(0,0,0,0.15); border-radius: 4px; }
        .toc-title { font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; }
        .toc-entry { margin-top: 10px; margin-bottom: 5px; font-weight: bold; font-size: 1.1em; }
        .toc-entry a { text-decoration: none; color: #000; display: block; }
        .toc-entry a::after { content: leader('.') target-counter(attr(href), page); float: right; font-weight: normal;}

        .local-toc-box { background: #fcfcfc; border: 1px solid #e0e0e0; padding: 15px; margin-bottom: 30px; border-radius: 4px; page-break-inside: auto; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
        .local-toc-title { font-weight: bold; margin-bottom: 10px; color: #555; border-bottom: 1px solid #eee; padding-bottom: 5px;}
        .local-toc-entry { font-size: 0.95em; margin-bottom: 4px; padding-left: 0; }
        .local-toc-entry a { text-decoration: none; color: #333; display: block; }
        .local-toc-entry a::after { content: leader('.') target-counter(attr(href), page); float: right; color: #888; }
        .local-toc-model { font-size: 0.95em; margin-left: 20px; margin-bottom: 6px; }
        .local-toc-model a { text-decoration: none; color: #666; }
        .local-toc-model a:hover { text-decoration: none; }
        .local-toc-model a::after { content: leader('.') target-counter(attr(href), page); float: right; color: #888; }

        .legend-box { border: 1px solid #ccc; background: #f9f9f9; padding: 15px; margin-bottom: 30px; font-size: 0.9em; page-break-inside: avoid; }
        .legend-item { display: flex; align-items: center; margin-bottom: 5px; }
        .legend-color { width: 20px; height: 20px; margin-right: 10px; border-radius: 4px; border: 1px solid #ccc;}
        .turn-container { margin-bottom: 25px; page-break-inside: avoid; border-bottom: 1px solid #eee; padding-bottom: 15px; }
        .turn-header { background: #f8f9fa; padding: 5px 10px; font-size: 0.75rem; color: #666; font-weight: bold; display: flex; justify-content: center; border: 1px solid #eee; border-bottom: none; border-radius: 4px 4px 0 0; margin-bottom: 0; position: relative;}
        .turn-id { position: absolute; right: 10px; color: #999; font-family: monospace; font-size: 0.7rem; font-weight: normal; }
        .turn-body { padding: 10px; border: 1px solid #eee; border-top: none; border-radius: 0 0 4px 4px; }
        .bubble-user { background-color: #e8f0fe; border-left: 4px solid #1967d2; padding: 10px 15px; border-radius: 8px; margin-bottom: 10px; font-size: 0.95em; }
        .bubble-model { background-color: #fff; border: 1px solid #eee; padding: 10px 15px; border-radius: 8px; font-size: 1em; }
        .role-label { font-weight: bold; font-size: 0.75em; text-transform: uppercase; margin-bottom: 5px; display: block; }
        .lbl-user { color: #1967d2; }
        .lbl-model { color: #5f6368; }
        pre { background: #f5f5f5; padding: 10px; border-radius: 5px; font-family: 'Consolas', monospace; font-size: 0.85em; white-space: pre-wrap; word-wrap: break-word; page-break-inside: avoid; border: 1px solid #ddd; }
        img { max-width: 100%; height: auto; display: block; margin: 10px 0; }
        .meta-data { font-size: 0.85em; color: #666; margin-bottom: 20px; background: #fff; padding: 10px; border: 1px solid #eee; }
        .print-url { font-style: italic; color: #555; word-break: break-all; font-size: 0.9em; }
        .page-break { page-break-before: always; }
        """

    def _generate_book_pdf_single(self, chat, output_path):
        self._generate_pdf_logic([chat], output_path, single_mode=True)

    def _generate_book_pdf_merged_from_json(self, metadata_list, output_path):
        self._generate_pdf_logic(metadata_list, output_path, single_mode=False, load_from_json=True)

    def _generate_pdf_logic(self, data_list, output_path, single_mode=False, load_from_json=False):
        temp_html_path = output_path + ".temp.html"
        try:
            with open(temp_html_path, "w", encoding="utf-8") as f:
                f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>")
                # Deckblatt
                f.write(f"""
                <div style="text-align:center; padding-top: 100px;">
                    <h1 style="border:none;">KI-Dokumentation</h1>
                    <p>Generiert am: {datetime.now().strftime('%d.%m.%Y um %H:%M')}</p>
                    <p>Anzahl der Chats: {len(data_list)}</p>
                </div>
                <div class="page-break"></div>
                <div class="legend-header"></div>
                <h2>Legende & Hinweise</h2>
                <div class="legend-box">
                    <p><strong>Definition: Was ist ein "Turn"?</strong></p>
                    <p>Ein "Turn" bezeichnet einen einzelnen Interaktionsschritt im Dialog.</p>
                    <hr style="border:0; border-top:1px solid #ddd; margin: 10px 0;">
                    <div class="legend-item"><div class="legend-color" style="background: #e8f0fe; border-color: #1967d2;"></div><span><strong>USER</strong></span></div>
                    <div class="legend-item"><div class="legend-color" style="background: #fff; border-color: #eee;"></div><span><strong>MODEL</strong></span></div>
                </div>
                <div class="page-break"></div>
                """)

                # Global TOC
                if not single_mode and len(data_list) > 1:
                    f.write(
                        """<div class="toc-header-marker"><div class="toc-title">Inhaltsverzeichnis</div><div class="toc">""")
                    for i, item in enumerate(data_list):
                        title = item['title']
                        f.write(
                            f"""<div class="toc-entry"><a href="#chat_{i}">{i + 1}. {html.escape(title)}</a></div>""")
                    f.write("</div></div><div class='page-break'></div>")

                for i, item in enumerate(data_list):
                    try:
                        if load_from_json:
                            with open(item['json_path'], "r", encoding="utf-8") as jf:
                                chat = json.load(jf)
                        else:
                            chat = item

                        chat_id = f"chat_{i}"
                        if not single_mode and i > 0: f.write("""<div class="page-break"></div>""")

                        screen_abs = chat.get('screenshot_path_abs', '')
                        screen_src = pathlib.Path(screen_abs).as_uri() if screen_abs and os.path.exists(
                            screen_abs) else ""
                        img_tag = f'<img src="{screen_src}" class="title-screenshot" alt="Titelbild">' if screen_src else ''

                        local_toc = """<div class="local-toc-box"><div class="local-toc-title">Inhalt dieses Chats</div>"""
                        for t in chat['turns']:
                            disp_text = self._get_toc_display_text(t)
                            local_toc += f"""<div class="local-toc-entry"><a href="#{chat_id}_turn_{t['index']}">{html.escape(disp_text)}</a></div>"""
                            if self.include_model_toc:
                                local_toc += f"""<div class="local-toc-model"><a href="#{chat_id}_turn_{t['index']}_model">↳ KI-Antwort</a></div>"""
                        local_toc += "</div>"

                        f.write(f"""
                        <div id="{chat_id}">
                            <h1 class="chapter-title">{i + 1}. {html.escape(chat['title'])}</h1>
                            {img_tag}
                            <div class="meta-data">
                                <b>Modell:</b> {chat['model']} | <b>Zeitpunkt:</b> {chat['original_date']} <br>
                                <a href="{chat['url']}" style="color:#666;">Original Chat Link</a> <span class="print-url">( {chat['url']} )</span>
                            </div>
                            {local_toc}
                        """)

                        for t in chat['turns']:
                            turn_full_id = f"chat_{i + 1}_turn_{t['index']}"
                            short_header = self._get_short_header_text(t['user'])
                            user_html = self._render_markdown(t['user'])
                            model_html = self._render_markdown(t['model'])

                            u_imgs_html = ""
                            if t['images']:
                                for img_rel in t['images']:
                                    abs_p = os.path.abspath(os.path.join(self.dirs['base'], img_rel))
                                    if os.path.exists(abs_p):
                                        u_imgs_html += f'<img src="{pathlib.Path(abs_p).as_uri()}">'

                            f.write(f"""
                            <div id="{chat_id}_turn_{t['index']}" class="turn-container">
                                <div class="turn-header-marker" data-title="{html.escape(short_header)}" data-num="TURN #{t['index']}"></div>
                                <div class='turn-header'>
                                    <span class="turn-header-text">TURN #{t['index']}</span>
                                    <span class='turn-id'>{turn_full_id}</span>
                                </div>
                                <div class="turn-body">
                                    <div class="bubble-user"><span class="role-label lbl-user">User</span>{user_html}{u_imgs_html}</div>
                                    <div id="{chat_id}_turn_{t['index']}_model" class="bubble-model"><span class="role-label lbl-model">Model</span>{model_html}</div>
                                </div>
                            </div>
                            """)
                        f.write("</div>")
                        f.flush()
                        del chat
                    except Exception as loop_e:
                        self.log(f"PDF Loop Error: {loop_e}")
                        continue
                f.write("</body></html>")

            base_url = f"file://{os.path.abspath(self.dirs['base'])}/"
            font_config = FontConfiguration()
            HTML(filename=temp_html_path, base_url=base_url).write_pdf(output_path, stylesheets=[
                CSS(string=self._get_common_pdf_css(), font_config=font_config)], font_config=font_config)
        except Exception as e:
            self.log(f"PDF Gen Error: {e}")
            traceback.print_exc()
        finally:
            if os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except:
                    pass

    def _create_merged_file_from_json(self, metadata_list, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Merged Chats</title>{self._get_browser_css()}</head><body>")

                f.write(
                    "<div class='sidebar'><div class='sidebar-header'><h3>Inhaltsverzeichnis</h3></div><div class='sidebar-content'>")
                for i, item in enumerate(metadata_list):
                    f.write(f"<div class='toc-chat-title'>{html.escape(item['title'])}</div>")
                    try:
                        with open(item['json_path'], "r", encoding="utf-8") as jf:
                            chat = json.load(jf)
                        for t in chat['turns']:
                            turn_id = f"chat_{i}_turn_{t['index']}"
                            disp_text = self._get_toc_display_text(t)
                            f.write(
                                f"<a href='#{turn_id}' class='toc-turn-link' title='{html.escape(t['user'][:100])}'>{html.escape(disp_text)}</a>")
                    except:
                        pass
                f.write("</div></div><div class='main'>")
                for i, item in enumerate(metadata_list):
                    try:
                        with open(item['json_path'], "r", encoding="utf-8") as jf:
                            chat = json.load(jf)
                        f.write(
                            f"<div id='chat_{i}' class='chat-container'><div class='chat-meta'><h1>{html.escape(chat['title'])}</h1><div class='meta-info'><span class='meta-badge'>{chat['model']}</span> <span>📅 {chat['original_date']}</span></div></div>")
                        for t in chat['turns']:
                            turn_id = f"chat_{i}_turn_{t['index']}"
                            turn_full_id = f"chat_{i + 1}_turn_{t['index']}"
                            u = self._render_markdown(t['user']);
                            m = self._render_markdown(t['model']);
                            imgs = "".join([f"<img src='{x}'>" for x in t['images']])
                            f.write(
                                f"<div id='{turn_id}' class='turn-container'><div class='turn-header'><span>TURN #{t['index']}</span><span class='turn-id'>{turn_full_id}</span></div><div class='turn-body'><div class='role-user'><div class='role-label user'>USER</div><div class='bubble-content'><div class='content'>{u}</div>{imgs}</div></div><div class='role-model'><div class='role-label model'>MODEL</div><div class='bubble-content'><div class='content'>{m}</div></div></div></div></div>")
                        f.write("</div>")
                    except:
                        pass
                f.write("</div></body></html>")
        except Exception as e:
            self.log(f"Merged HTML Gen Error: {e}")

    def _render_template_browser(self, chats_list, start_index=0):
        toc_html = ""
        content_html = ""
        current_access_date = datetime.now().strftime('%d.%m.%Y um %H:%M')
        for i, chat in enumerate(chats_list):
            global_idx = start_index + i;
            chat_anchor = f"chat_{global_idx}"
            toc_html += f"<div class='toc-chat-title'>{html.escape(chat['title'])}</div>"
            content_html += f"<div id='{chat_anchor}' class='chat-container'><div class='chat-meta'><h1>{html.escape(chat['title'])}</h1><div class='meta-info'><span class='meta-badge'>{chat['model']}</span> <span>Chatverlauf vom: {chat['original_date']}</span> <span>Veröffentlicht am: {chat['publish_date']}</span></div><div class='meta-info'>Abgerufen am: {current_access_date} | <a href='{chat['url']}' target='_blank'>Original Link</a> <span style='color:gray; font-style:italic;'>(URL: {chat['url']})</span></div></div>"
            for t in chat['turns']:
                turn_id = f"{chat_anchor}_turn_{t['index']}";
                turn_full_id = f"chat_{chat.get('id_number', 1)}_turn_{t['index']}"
                disp_text = self._get_toc_display_text(t)
                full_tooltip = html.escape(t['user'].strip())
                toc_html += f"<a href='#{turn_id}' class='toc-turn-link' title='{full_tooltip}'>{html.escape(disp_text)}</a>"
                u = self._render_markdown(t['user']);
                m = self._render_markdown(t['model']);
                imgs = "".join([f"<img src='{x}'>" for x in t['images']])
                content_html += f"<div id='{turn_id}' class='turn-container'><div class='turn-header'><span>TURN #{t['index']}</span><span class='turn-id'>{turn_full_id}</span></div><div class='turn-body'><div class='role-user'><div class='role-label user'>USER</div><div class='bubble-content'><div class='content'>{u}</div>{imgs}</div></div><div class='role-model'><div class='role-label model'>MODEL</div><div class='bubble-content'><div class='content'>{m}</div></div></div></div></div>"
            content_html += "</div>"
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Gemini Export</title>{self._get_browser_css()}</head><body><div class='sidebar'><div class='sidebar-header'><h3>Inhaltsverzeichnis</h3></div><div class='sidebar-content'>{toc_html}</div></div><div class='main'>{content_html}</div></body></html>"

    def _get_browser_css(self):
        return """<style>body{margin:0;padding:0;font-family:'Segoe UI';background:#f0f2f5;height:100vh;display:flex;overflow:hidden;} .sidebar{width:350px;background:#fff;border-right:1px solid #ddd;display:flex;flex-direction:column;flex-shrink:0;} .sidebar-header{padding:15px;border-bottom:1px solid #eee;background:#f8f9fa;} .sidebar-content{flex:1;overflow-y:auto;padding:10px;} .toc-chat-title{font-weight:bold;margin-top:15px;margin-bottom:5px;color:#1a73e8;font-size:0.95rem;padding-left:10px;} .toc-turn-link{display:block;padding:4px 10px;color:#555;text-decoration:none;font-size:0.85rem;border-left:2px solid transparent;margin-left:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;} .toc-turn-link:hover{background:#f1f3f4;color:#333;border-left-color:#1a73e8;} .main{flex:1;overflow-y:auto;padding:40px;scroll-behavior:smooth;} .chat-container{max-width:950px;margin:0 auto 60px;background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);} .chat-meta{padding:20px;border-bottom:1px solid #eee;background:#fff;border-radius:8px 8px 0 0;} .meta-info{font-size:0.9rem;color:#666;margin-top:5px;display:flex;gap:15px;align-items:center;flex-wrap:wrap;} .meta-badge{background:#e8f0fe;color:#1967d2;padding:3px 8px;border-radius:4px;font-weight:bold;font-size:0.8rem;} .turn-container{border-bottom:1px solid #f0f0f0;padding:0;} .turn-header{background:#f8f9fa;padding:8px 20px;font-size:0.75rem;color:#666;font-weight:bold;display:flex;justify-content:space-between;border-bottom:1px solid #f1f1f1;} .turn-id{color:#999;font-family:monospace;} .turn-body{padding:20px;display:flex;flex-direction:column;gap:15px;} .role-user{background:#e8f0fe;border-radius:12px;align-self:flex-start;max-width:90%;border-left:4px solid #1967d2;padding:0;overflow:hidden;} .role-model{background:#ffffff;border-radius:12px;max-width:100%;border:1px solid #eee;padding:0;overflow:hidden;} .role-label{font-size:0.7rem;font-weight:bold;letter-spacing:1px;padding:5px 15px;text-transform:uppercase;border-bottom:1px solid rgba(0,0,0,0.05);} .role-label.user{background:rgba(25,103,210,0.1);color:#1967d2;} .role-label.model{background:#f8f9fa;color:#5f6368;} .bubble-content{padding:15px;} .content p{margin-top:0;} img{max-width:100%;border-radius:6px;border:1px solid #ddd;margin-top:10px;}</style>"""

    def _create_index_file(self, metadata_list):
        if self.detailed_index:
            rows = ""
            for item in metadata_list:
                screen = f"screenshots/{item.get('screenshot_filename', '')}"
                rows += f"""<tr class="chat-row"><td style="text-align:center;font-weight:bold;">{item['id_number']}</td>
                <td style="position:relative;"><strong>Thema:</strong> {item['title']}<br><a href='{item['url']}' target='_blank' style="font-size:0.9em;color:#1a73e8;">[Originalchat Link]</a>
                <div class="preview-popup"><img src="{screen}" onerror="this.style.display='none'"></div></td>
                <td style="white-space:nowrap;"><strong>Chatverlauf vom:</strong> {item['original_date']}<br><strong>Veröffentlicht am:</strong> {item['publish_date']}</td>
                <td><strong>Modell:</strong> {item['model']}<br><strong>Datei:</strong> <a href='{item['filename']}'>{item['filename']}</a></td></tr>"""
            html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>KI-Verzeichnis</title><style>body{{font-family:'Segoe UI';padding:30px;color:#333;}}table{{width:100%;border-collapse:collapse;margin-top:20px;}}th{{background:#eee;text-align:left;padding:10px;border:1px solid #ccc;}}td{{border:1px solid #ccc;padding:10px;vertical-align:top;}}tr:nth-child(even){{background:#f9f9f9;}}a{{text-decoration:none;color:#1a73e8;}}.preview-popup{{display:none;position:absolute;left:102%;top:0;width:350px;border:2px solid #333;background:#fff;z-index:99;}}td:hover .preview-popup{{display:block;}}img{{width:100%;}}</style></head><body><h1>Anlage: KI-Verzeichnis <span style="float:right;font-size:0.6em;color:#555;">Abgerufen am: {datetime.now().strftime('%d.%m.%Y um %H:%M')}</span></h1><table><tr><th style="width:50px;">Nr.</th><th>Thema & Quellenverweis</th><th style="width:250px;">Datumsangaben</th><th style="width:250px;">Modell & Datei</th></tr>{rows}</table></body></html>"""
        else:
            rows = ""
            for item in metadata_list:
                rows += f"<tr><td>{item['id_number']}</td><td><a href='{item['filename']}'>{item['title']}</a></td><td>{item['original_date']}</td></tr>"
            html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Index</title><style>body{{font-family:sans-serif;padding:20px;}}table{{width:100%;border-collapse:collapse;}}td,th{{border:1px solid #ddd;padding:8px;text-align:left;}}tr:nth-child(even){{background-color:#f2f2f2;}}</style></head><body><h1>Chat Index</h1><table><tr><th>ID</th><th>Titel</th><th>Datum</th></tr>{rows}</table></body></html>"""

        with open(os.path.join(self.dirs['final'], "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    def _extract_dom_data(self, html, url):
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.find('h1', class_='headline').get_text(strip=True) if soup.find('h1',
                                                                                         class_='headline') else "Gemini Chat"
            full_text = soup.get_text(" ", strip=True)

            # MODEL REGEX FIX
            if m := re.search(r'Erstellt mit\s+(.+?)(?=\s\d)', full_text):
                model = m.group(1).strip()
            else:
                model = "Gemini"

            date_regex = r'(\d{1,2}\.?\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|\d{1,2}\.?)\s+\d{4}(?:\s+um\s+\d{1,2}:\d{2})?)'
            match_pub = re.search(r'Veröffentlicht.*?' + date_regex, full_text, re.IGNORECASE)
            pub = match_pub.group(1) if match_pub else datetime.now().strftime("%d.%m.%Y")
            match_orig = re.search(r'Weitere Informationen.*?' + date_regex, full_text, re.IGNORECASE)
            if match_orig:
                orig = match_orig.group(1)
            else:
                simple_match = re.search(date_regex, full_text)
                orig = simple_match.group(1) if simple_match else datetime.now().strftime("%d.%m.%Y")

            turns = []
            for idx, c in enumerate(soup.find_all('share-turn-viewer')):
                t = {"index": idx + 1, "user": "", "model": "", "images": []}
                if uq := c.find('user-query'):
                    # WORKAROUND
                    raw_user = self._brute_force_sanitize(uq.decode_contents())
                    for img in uq.find_all('img'):
                        if src := self._get_img_src(img): t['images'].append(src)
                    t['user'] = markdownify.markdownify(raw_user, heading_style="ATX").strip()
                if rc := c.find('response-container'):
                    if md := rc.find('div', class_='markdown'):
                        for img in md.find_all('img'):
                            if src := self._get_img_src(img): img.replace_with(f"\n[IMG:{src}]\n")
                        for cb in md.find_all('code-block'):
                            if pre := cb.find('pre'):
                                new_pre = soup.new_tag("pre");
                                new_pre.string = pre.get_text();
                                cb.replace_with(new_pre)

                        raw_model = self._brute_force_sanitize(md.decode_contents())
                        t['model'] = markdownify.markdownify(raw_model, heading_style="ATX").strip()
                if t['user'] or t['model']: turns.append(t)
            return {"title": title, "original_date": orig, "publish_date": pub, "model": model, "url": url,
                    "turns": turns}, "Success"
        except Exception as e:
            return None, str(e)