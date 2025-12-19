# gemini_chat_grabber
Automated exporter for Google Gemini chats. Converts shared chat URLs into offline-viewable HTML files, preserving formatting, code blocks, and images. Includes a GUI for easy batch processing and local archiving.

License: This work is licensed under the Creative Commons BY NC ND License (https://creativecommons.org/licenses/by-nc-nd/4.0/), please see LICENSE File for further information.

# Prerequirements:
Python 3.12

Please execute "pip install requirements.txt" 

Additional required:
- gtk3-runtime-3.24.31 (Setup with \bin directory and added to PATH),
- SQL Database (run web_crawl_v32.sql to create tables)
- install Playwright/Selenium

# Setup
- run main.py to launch the GUI
- setup database using the GUI
- open urls.txt with gemini chat URLs
- use GUI to create browser session (login, click cookieconsent etc.) and close window again
- choose options for crawling and export file/files
- click Go to start export
You will see the Browser window of each crawl to be able to click browser consent if required.
Sit down and relax during the crawl. The crawler will do it for you.

# Info
The gemini crawler will create an output folder with information of the crawl.
Inside crawl folder you find, depending on your choosen output options:
- pdf folder includes all PDF files
- crawl_data includes images of the chat
- raw_crawl_data includes raw html export (mostly only required for debugging)
- screenshots includes a screenshot of each crawl
- index.html and html files of each crawl will be generated in the crawl output folder for each crawl

Additional Database Features have been implemented to give you advanced granular prompt export function
Each crawl will be stored to the Database automatically. You could choose database only to store data only in database.

general crawler is deprecated, it's just a historical element that consents to crawl functionality of other webpages than gemini-chats