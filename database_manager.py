# database_manager.py
# Version: 14.0 (Stable)
import mysql.connector
import datetime
import json


class DatabaseManager:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except:
            return {}

    def get_connection(self):
        return mysql.connector.connect(
            host=self.config.get("db_host", "localhost"),
            user=self.config.get("db_user", "root"),
            password=self.config.get("db_password", ""),
            database=self.config.get("db_name", "web_crawl")
        )

    def init_db(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            table_name = "gemini_crawler_data"

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    content LONGTEXT,
                    json_data LONGTEXT,
                    crawler_type VARCHAR(50),
                    file_path TEXT,
                    crawled_at DATETIME
                )
            """)
            conn.commit()

            # Migration check
            try:
                cursor.execute(f"SELECT json_data FROM {table_name} LIMIT 1")
            except:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN json_data LONGTEXT")
                conn.commit()

            conn.close()
            return True, f"Datenbank '{table_name}' bereit."
        except Exception as e:
            return False, f"DB Fehler: {e}"

    def save_content(self, url, title, html_content, json_content, crawler_type, file_path=""):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            json_str = json.dumps(json_content, ensure_ascii=False) if isinstance(json_content, dict) else json_content

            sql = f"INSERT INTO gemini_crawler_data (url, title, content, json_data, crawler_type, file_path, crawled_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(sql, (url, title, html_content, json_str, crawler_type, file_path, datetime.datetime.now()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Save Error: {e}")
            return False

    def search_documents(self, query):
        """Suche auf Dokumentenebene."""
        results = []
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            ptn = f"%{query}%"
            sql = "SELECT id, title, crawled_at, url, json_data FROM gemini_crawler_data WHERE title LIKE %s OR content LIKE %s ORDER BY crawled_at DESC LIMIT 100"
            cursor.execute(sql, (ptn, ptn))
            results = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"Doc Search Error: {e}")
        return results

    def search_granular_turns(self, query):
        """Suche in Turns (JSON)."""
        hits = []
        candidates = self.search_documents(query)
        query_lower = query.lower()

        for row in candidates:
            try:
                if not row['json_data']: continue
                data = json.loads(row['json_data'])
                turns = data.get('turns', [])

                for t in turns:
                    user_txt = t.get('user', '').lower()
                    model_txt = t.get('model', '').lower()

                    if query_lower in user_txt or query_lower in model_txt:
                        snippet = t.get('user', '')[:100].replace('\n', ' ')
                        hits.append({
                            'chat_id': row['id'],
                            'chat_title': row['title'],
                            'date': row['crawled_at'],
                            'turn_index': t['index'],
                            'snippet': snippet,
                            'full_turn_data': t,
                            'full_chat_meta': {k: v for k, v in row.items() if k != 'json_data'}
                        })
            except:
                continue
        return hits

    def get_entry_by_id(self, entry_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM gemini_crawler_data WHERE id = %s", (entry_id,))
            res = cursor.fetchone()
            conn.close()
            return res
        except:
            return None