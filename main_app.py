# main_app.py
# Version: 27.0 (Stable)
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, Toplevel
import multiprocessing
import queue
import json
import os
import threading
import webbrowser
import datetime

from gemini_crawler import GeminiCrawlerProcess
from general_crawler import GeneralCrawlerProcess
from auth_handler import AuthHandler
from database_manager import DatabaseManager


def run_gemini_worker(urls, q, config, mode, pdf_export, model_toc, index_only, duplex_mode, detailed_index, save_raw,
                      page_num_pos, out_dir):
    worker = GeminiCrawlerProcess(urls, q, config,
                                  export_mode=mode,
                                  pdf_export=pdf_export,
                                  include_model_toc=model_toc,
                                  index_only=index_only,
                                  duplex_mode=duplex_mode,
                                  detailed_index=detailed_index,
                                  save_raw=save_raw,
                                  page_num_pos=page_num_pos,
                                  base_output_dir=out_dir)
    worker.run()


def run_db_export_worker(chat_data_list, q, config, pdf_export, model_toc, duplex_mode, detailed_index, out_dir, title):
    worker = GeminiCrawlerProcess([], q, config,
                                  export_mode="all",
                                  pdf_export=pdf_export,
                                  include_model_toc=model_toc,
                                  duplex_mode=duplex_mode,
                                  detailed_index=detailed_index,
                                  base_output_dir=out_dir)
    worker.run_export_from_db(chat_data_list, custom_title=title)


def run_general_worker(urls, q, config):
    worker = GeneralCrawlerProcess(urls, q, config);
    worker.run()


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Modular Web Spider v27.0")
        self.root.geometry("1400x950")
        self.log_queue = multiprocessing.Queue()
        self.output_path = os.path.join(os.getcwd(), "output")
        self.db = DatabaseManager()

        self.doc_search_results = []
        self.granular_search_results = []
        self.export_queue = []

        self._setup_ui()
        self._check_queue()
        self.refresh_db_status()

    def refresh_db_status(self):
        ok, msg = self.db.init_db();
        self.log(f"DB: {msg}")

    def _setup_ui(self):
        tab_control = ttk.Notebook(self.root)
        tab_crawl = ttk.Frame(tab_control)
        tab_docs = ttk.Frame(tab_control)
        tab_granular = ttk.Frame(tab_control)

        tab_control.add(tab_crawl, text="🕷️ Crawler")
        tab_control.add(tab_docs, text="📚 Dokumenten-Suche")
        tab_control.add(tab_granular, text="🔬 Granulare Suche")
        tab_control.pack(expand=1, fill="both")

        self._setup_crawler_tab_restored(tab_crawl)
        self._setup_doc_search_tab(tab_docs)
        self._setup_granular_search_tab(tab_granular)

        queue_frame = ttk.Frame(self.root, padding=5, relief="raised")
        queue_frame.pack(fill="x", side="bottom")
        self.lbl_queue = ttk.Label(queue_frame, text="Sammelmappe: 0 Elemente")
        self.lbl_queue.pack(side="left", padx=10)
        ttk.Button(queue_frame, text="📂 Sammelmappe öffnen & Exportieren", command=self.open_export_queue_window).pack(
            side="right")

        log_frame = ttk.LabelFrame(self.root, text="System Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=8, state="disabled", bg="#1e1e1e", fg="#00ff00",
                                                 font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True)

    def _setup_crawler_tab_restored(self, parent):
        toolbar = ttk.Frame(parent, padding=5);
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="🔑 Login Browser", command=self.open_auth).pack(side="left", padx=5)
        ttk.Button(toolbar, text="📂 URLs laden", command=self.load_urls_from_file).pack(side="left", padx=5)
        ttk.Button(toolbar, text="⚙️ DB Config", command=self.open_db_settings_window).pack(side="right", padx=5)

        lbl_urls = ttk.Label(parent, text="Target URLs:");
        lbl_urls.pack(anchor="w", padx=10, pady=(10, 0))
        self.txt_urls = scrolledtext.ScrolledText(parent, height=10);
        self.txt_urls.pack(fill="x", padx=10, pady=5)

        ctrl = ttk.LabelFrame(parent, text="Einstellungen", padding=10);
        ctrl.pack(fill="x", padx=10, pady=10)

        path_frame = ttk.Frame(ctrl);
        path_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(path_frame, text="Output:").pack(side="left")
        self.lbl_path = ttk.Label(path_frame, text=self.output_path, background="#e1e1e1", relief="sunken", padding=2)
        self.lbl_path.pack(side="left", fill="x", expand=True, padx=10)
        ttk.Button(path_frame, text="Wählen...", command=self.choose_directory).pack(side="left")

        opts_grid = ttk.Frame(ctrl);
        opts_grid.pack(fill="x")

        c1 = ttk.LabelFrame(opts_grid, text="Modus");
        c1.pack(side="left", fill="y", padx=5)
        self.export_var = tk.StringVar(value="all")
        ttk.Radiobutton(c1, text="Einzeln", variable=self.export_var, value="single").pack(anchor="w")
        ttk.Radiobutton(c1, text="Zusammen", variable=self.export_var, value="merged").pack(anchor="w")
        ttk.Radiobutton(c1, text="Alles", variable=self.export_var, value="all").pack(anchor="w")

        c2 = ttk.LabelFrame(opts_grid, text="Layout");
        c2.pack(side="left", fill="y", padx=5)
        self.pdf_var = tk.BooleanVar(value=True);
        self.duplex_var = tk.BooleanVar(value=False)
        self.model_toc_var = tk.BooleanVar(value=False);
        self.detailed_index_var = tk.BooleanVar(value=True)
        self.page_pos_var = tk.StringVar(value="bottom")

        ttk.Checkbutton(c2, text="PDF", variable=self.pdf_var, command=self._toggle_opts).pack(anchor="w")
        self.ck_duplex = ttk.Checkbutton(c2, text="Duplex", variable=self.duplex_var);
        self.ck_duplex.pack(anchor="w", padx=10)
        self.ck_toc = ttk.Checkbutton(c2, text="KI im TOC", variable=self.model_toc_var);
        self.ck_toc.pack(anchor="w", padx=10)

        f_pos = ttk.Frame(c2);
        f_pos.pack(anchor="w", padx=10)
        ttk.Label(f_pos, text="Seitenzahl:").pack(side="left")
        ttk.OptionMenu(f_pos, self.page_pos_var, "bottom", "bottom", "top").pack(side="left")

        ttk.Checkbutton(c2, text="Rich Index", variable=self.detailed_index_var).pack(anchor="w")

        c3 = ttk.LabelFrame(opts_grid, text="DB & Debug");
        c3.pack(side="left", fill="y", padx=5)
        self.index_only_var = tk.BooleanVar(value=False)
        self.save_raw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(c3, text="Nur Indexieren", variable=self.index_only_var).pack(anchor="w")
        ttk.Checkbutton(c3, text="Raw HTML speichern", variable=self.save_raw_var).pack(anchor="w")

        btn_frame = ttk.Frame(parent, padding=10);
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="🚀 START GEMINI", command=self.start_gemini).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_frame, text="🌐 GENERAL CRAWLER", command=self.start_general).pack(side="right", fill="x",
                                                                                         expand=True, padx=(10, 0))

    def _setup_doc_search_tab(self, parent):
        top = ttk.Frame(parent, padding=10);
        top.pack(fill="x")
        self.entry_doc_search = ttk.Entry(top, width=50);
        self.entry_doc_search.pack(side="left", padx=10)
        self.entry_doc_search.bind("<Return>", lambda e: self.do_doc_search())
        ttk.Button(top, text="Suchen", command=self.do_doc_search).pack(side="left")
        self.tree_docs = ttk.Treeview(parent, columns=("check", "id", "title", "date"), show="headings")
        self.tree_docs.heading("check", text="[x]");
        self.tree_docs.column("check", width=30)
        self.tree_docs.heading("id", text="ID");
        self.tree_docs.column("id", width=40)
        self.tree_docs.heading("title", text="Titel");
        self.tree_docs.column("title", width=400)
        self.tree_docs.heading("date", text="Datum");
        self.tree_docs.column("date", width=120)
        self.tree_docs.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_docs.bind("<Button-1>", self.on_doc_click)
        self.tree_docs.bind("<Double-1>", self.on_doc_double_click)
        ttk.Button(parent, text="Markierte zur Sammelmappe", command=self.add_docs_to_queue).pack(pady=5)

    def _setup_granular_search_tab(self, parent):
        top = ttk.Frame(parent, padding=10);
        top.pack(fill="x")
        self.entry_gran_search = ttk.Entry(top, width=50);
        self.entry_gran_search.pack(side="left", padx=10)
        self.entry_gran_search.bind("<Return>", lambda e: self.do_gran_search())
        ttk.Button(top, text="Suchen", command=self.do_gran_search).pack(side="left")
        self.tree_gran = ttk.Treeview(parent, columns=("check", "chat", "turn", "snippet"), show="headings")
        self.tree_gran.heading("check", text="[x]");
        self.tree_gran.column("check", width=30)
        self.tree_gran.heading("chat", text="Chat");
        self.tree_gran.column("chat", width=200)
        self.tree_gran.heading("turn", text="#");
        self.tree_gran.column("turn", width=40)
        self.tree_gran.heading("snippet", text="Inhalt");
        self.tree_gran.column("snippet", width=600)
        self.tree_gran.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_gran.bind("<Button-1>", self.on_gran_click)
        self.tree_gran.bind("<Double-1>", self.on_gran_double_click)
        ttk.Button(parent, text="Markierte zur Sammelmappe", command=self.add_gran_to_queue).pack(pady=5)

    def _toggle_opts(self):
        st = "normal" if self.pdf_var.get() else "disabled"
        self.ck_duplex.config(state=st);
        self.ck_toc.config(state=st)

    def do_doc_search(self):
        q = self.entry_doc_search.get();
        if not q: return
        self.doc_search_results = []
        for i in self.tree_docs.get_children(): self.tree_docs.delete(i)
        hits = self.db.search_documents(q)
        for h in hits:
            h['checked'] = False;
            self.doc_search_results.append(h)
            h['tree_id'] = self.tree_docs.insert("", "end", values=("☐", h['id'], h['title'], h['crawled_at']))

    def do_gran_search(self):
        q = self.entry_gran_search.get();
        if not q: return
        self.granular_search_results = []
        for i in self.tree_gran.get_children(): self.tree_gran.delete(i)
        hits = self.db.search_granular_turns(q)
        for h in hits:
            h['checked'] = False;
            self.granular_search_results.append(h)
            h['tree_id'] = self.tree_gran.insert("", "end",
                                                 values=("☐", h['chat_title'], h['turn_index'], h['snippet']))

    def on_doc_click(self, event):
        self._handle_click(event, self.tree_docs, self.doc_search_results)

    def on_gran_click(self, event):
        self._handle_click(event, self.tree_gran, self.granular_search_results)

    def _handle_click(self, event, tree, data_list):
        region = tree.identify("region", event.x, event.y)
        if region == "cell":
            col = tree.identify_column(event.x)
            if col == "#1":
                row_id = tree.identify_row(event.y)
                for item in data_list:
                    if item.get('tree_id') == row_id:
                        item['checked'] = not item['checked']
                        sym = "☒" if item['checked'] else "☐"
                        vals = tree.item(row_id, "values")
                        tree.item(row_id, values=(sym, *vals[1:]))
                        break

    def on_doc_double_click(self, event):
        item_id = self.tree_docs.selection()
        if not item_id: return
        for item in self.doc_search_results:
            if item['tree_id'] == item_id[0]:
                if item.get('json_data'):
                    try:
                        self._generate_preview_html(json.loads(item['json_data']))
                    except:
                        pass
                break

    def on_gran_double_click(self, event):
        item_id = self.tree_gran.selection()
        if not item_id: return
        for item in self.granular_search_results:
            if item['tree_id'] == item_id[0]:
                t = item['full_turn_data']
                fake_chat = {'title': f"Turn {item['turn_index']}", 'turns': [{'user': t['user'], 'model': t['model']}]}
                self._generate_preview_html(fake_chat)
                break

    def _generate_preview_html(self, chat_data):
        style = """<style>body{font-family:'Segoe UI';padding:20px;background:#f0f2f5}.chat{max-width:800px;margin:auto;background:#fff;padding:20px;border-radius:8px}.user{background:#e8f0fe;padding:10px;border-radius:8px;margin-bottom:10px;border-left:4px solid #1967d2}.model{background:#fff;padding:10px;border:1px solid #eee;border-radius:8px;margin-bottom:20px}</style>"""
        html = f"<html><head>{style}</head><body><div class='chat'><h2>{chat_data.get('title', 'Preview')}</h2>"
        for t in chat_data.get('turns', []):
            u = t.get('user', '').replace('\n', '<br>');
            m = t.get('model', '').replace('\n', '<br>')
            html += f"<div class='user'><b>USER:</b><br>{u}</div><div class='model'><b>MODEL:</b><br>{m}</div>"
        html += "</div></body></html>"
        tmp = os.path.join(self.output_path, "preview.html")
        with open(tmp, "w", encoding="utf-8") as f: f.write(html)
        webbrowser.open(f"file://{os.path.abspath(tmp)}")

    def add_docs_to_queue(self):
        added = 0
        for item in self.doc_search_results:
            if item['checked']:
                if item.get('json_data'):
                    try:
                        c = json.loads(item['json_data'])
                        self.export_queue.append({'type': 'chat', 'data': c, 'label': f"Dokument: {c['title']}"})
                        added += 1
                        item['checked'] = False
                    except:
                        pass
        self.update_queue_label(added);
        self._refresh_tree(self.tree_docs, self.doc_search_results)

    def add_gran_to_queue(self):
        added = 0
        for item in self.granular_search_results:
            if item['checked']:
                self.export_queue.append(
                    {'type': 'turn', 'data': item, 'label': f"Turn: {item['chat_title']} #{item['turn_index']}"})
                added += 1
                item['checked'] = False
        self.update_queue_label(added);
        self._refresh_tree(self.tree_gran, self.granular_search_results)

    def _refresh_tree(self, tree, data_list):
        for i in tree.get_children():
            vals = tree.item(i, "values")
            tree.item(i, values=("☐", *vals[1:]))

    def update_queue_label(self, added_count):
        self.lbl_queue.config(text=f"Sammelmappe: {len(self.export_queue)} Elemente")
        if added_count > 0: messagebox.showinfo("Info", f"{added_count} Elemente hinzugefügt.")

    def open_export_queue_window(self):
        if not self.export_queue: return messagebox.showwarning("Leer", "Sammelmappe ist leer.")

        win = Toplevel(self.root);
        win.title("Sammelmappe");
        win.geometry("700x500")

        frame_list = ttk.Frame(win);
        frame_list.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame_list)
        lst = tk.Listbox(frame_list, yscrollcommand=scrollbar.set)
        scrollbar.config(command=lst.yview)
        lst.pack(side="left", fill="both", expand=True);
        scrollbar.pack(side="right", fill="y")

        def refresh_list():
            lst.delete(0, "end")
            for i, item in enumerate(self.export_queue): lst.insert("end", f"{i + 1}. {item['label']}")

        refresh_list()

        def remove_selected():
            sel = lst.curselection()
            if not sel: return
            idx = sel[0]
            del self.export_queue[idx]
            refresh_list()
            self.lbl_queue.config(text=f"Sammelmappe: {len(self.export_queue)} Elemente")

        def clear():
            self.export_queue.clear();
            self.update_queue_label(0);
            win.destroy()

        def export():
            title = e_title.get() or "Sammel-Export"
            final_chats = []

            def create_partial_chat_structure(meta_dict, turns_list):
                orig_url = meta_dict.get('full_chat_meta', {}).get('url', 'DB')
                return {
                    "title": f"Auszug: {meta_dict['chat_title']}",
                    "original_date": meta_dict['date'].strftime('%d.%m.%Y') if meta_dict.get('date') else "Unbekannt",
                    "publish_date": datetime.datetime.now().strftime("%d.%m.%Y"),
                    "model": meta_dict.get('model', 'Auszug'),
                    "url": orig_url,
                    "turns": turns_list
                }

            current_chat_id = None;
            current_turns_buffer = [];
            current_meta_buffer = None

            for item in self.export_queue:
                if item['type'] == 'chat':
                    if current_turns_buffer:
                        final_chats.append(create_partial_chat_structure(current_meta_buffer, current_turns_buffer))
                        current_turns_buffer = [];
                        current_chat_id = None
                    final_chats.append(item['data'])
                elif item['type'] == 'turn':
                    t_data = item['data']['full_turn_data'];
                    meta = item['data']
                    if current_chat_id == meta['chat_id']:
                        current_turns_buffer.append(t_data)
                    else:
                        if current_turns_buffer: final_chats.append(
                            create_partial_chat_structure(current_meta_buffer, current_turns_buffer))
                        current_chat_id = meta['chat_id'];
                        current_meta_buffer = meta;
                        current_turns_buffer = [t_data]

            if current_turns_buffer: final_chats.append(
                create_partial_chat_structure(current_meta_buffer, current_turns_buffer))

            for chat in final_chats:
                for idx, t in enumerate(chat['turns']): t['index'] = idx + 1

            p = multiprocessing.Process(
                target=run_db_export_worker,
                args=(final_chats, self.log_queue, "config.json", self.pdf_var.get(),
                      self.model_toc_var.get(), self.duplex_var.get(), self.detailed_index_var.get(), self.output_path,
                      title)
            )
            p.start();
            win.destroy()

        f_bottom = ttk.Frame(win, padding=10);
        f_bottom.pack(fill="x")
        ttk.Button(f_bottom, text="Entfernen", command=remove_selected).pack(side="left")
        ttk.Button(f_bottom, text="Alle Löschen", command=clear).pack(side="left", padx=10)
        ttk.Label(f_bottom, text="Titel:").pack(side="left", padx=(20, 5))
        e_title = ttk.Entry(f_bottom, width=25);
        e_title.insert(0, "Mein Export");
        e_title.pack(side="left")
        ttk.Button(f_bottom, text="EXPORTIEREN", command=export).pack(side="right")

    def load_urls_from_file(self):
        p = filedialog.askopenfilename()
        if p:
            with open(p, "r") as f: self.txt_urls.delete("1.0", "end"); self.txt_urls.insert("end", f.read())

    def open_auth(self):
        threading.Thread(target=lambda: self.log_queue.put(f"System: {AuthHandler().open_browser_for_login()}")).start()

    def start_gemini(self):
        u = self.get_urls()
        if not u: return
        p = multiprocessing.Process(target=run_gemini_worker,
                                    args=(u, self.log_queue, "config.json", self.export_var.get(), self.pdf_var.get(),
                                          self.model_toc_var.get(), self.index_only_var.get(), self.duplex_var.get(),
                                          self.detailed_index_var.get(), self.save_raw_var.get(),
                                          self.page_pos_var.get(), self.output_path))
        p.start()

    def start_general(self):
        u = self.get_urls();
        if not u: return
        p = multiprocessing.Process(target=run_general_worker, args=(u, self.log_queue, "config.json"));
        p.start()

    def get_urls(self):
        return [l.strip() for l in self.txt_urls.get("1.0", "end").split('\n') if l.strip().startswith("http")]

    def log(self, msg):
        self.txt_log.config(state="normal"); self.txt_log.insert("end", f"{msg}\n"); self.txt_log.see(
            "end"); self.txt_log.config(state="disabled")

    def _check_queue(self):
        try:
            while True: self.log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._check_queue)

    def choose_directory(self):
        d = filedialog.askdirectory()
        if d: self.output_path = d; self.lbl_path.config(text=d)

    def open_db_settings_window(self):
        win = Toplevel(self.root);
        win.title("DB Einstellungen");
        win.geometry("400x300")
        try:
            with open("config.json", "r") as f:
                conf = json.load(f)
        except:
            conf = {}
        ttk.Label(win, text="Host:").pack();
        e1 = ttk.Entry(win);
        e1.insert(0, conf.get("db_host", "localhost"));
        e1.pack()
        ttk.Label(win, text="User:").pack();
        e2 = ttk.Entry(win);
        e2.insert(0, conf.get("db_user", "root"));
        e2.pack()
        ttk.Label(win, text="Pass:").pack();
        e3 = ttk.Entry(win, show="*");
        e3.insert(0, conf.get("db_password", ""));
        e3.pack()
        ttk.Label(win, text="DB:").pack();
        e4 = ttk.Entry(win);
        e4.insert(0, conf.get("db_name", "web_crawl"));
        e4.pack()

        def save():
            conf.update({"db_host": e1.get(), "db_user": e2.get(), "db_password": e3.get(), "db_name": e4.get()})
            with open("config.json", "w") as f: json.dump(conf, f, indent=4)
            self.refresh_db_status();
            win.destroy()

        ttk.Button(win, text="Speichern & Testen", command=save).pack(pady=10)