-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Erstellungszeit: 16. Dez 2025 um 12:40
-- Server-Version: 8.3.0
-- PHP-Version: 7.4.33

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Datenbank: `web_crawl_v32`
--

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `crawled_data`
--

DROP TABLE IF EXISTS `crawled_data`;
CREATE TABLE IF NOT EXISTS `crawled_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `run_id` int DEFAULT NULL,
  `parent_id` int DEFAULT NULL,
  `url` varchar(768) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  `title` text CHARACTER SET utf32 COLLATE utf32_bin,
  `description` text CHARACTER SET utf32 COLLATE utf32_bin,
  `raw_content` mediumtext CHARACTER SET utf32 COLLATE utf32_bin,
  `escaped_content` mediumtext CHARACTER SET utf32 COLLATE utf32_bin,
  `depth_level` int DEFAULT '0',
  `search_rank` int DEFAULT '0',
  `is_link_list` tinyint(1) DEFAULT '0',
  `crawled_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `content` longtext CHARACTER SET utf32 COLLATE utf32_bin,
  `crawler_type` varchar(50) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `run_id` (`run_id`)
) ENGINE=MyISAM AUTO_INCREMENT=17 DEFAULT CHARSET=utf32 COLLATE=utf32_bin;

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `gemini_crawler_data`
--

DROP TABLE IF EXISTS `gemini_crawler_data`;
CREATE TABLE IF NOT EXISTS `gemini_crawler_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `url` text CHARACTER SET utf32 COLLATE utf32_bin,
  `title` text CHARACTER SET utf32 COLLATE utf32_bin,
  `content` longtext CHARACTER SET utf32 COLLATE utf32_bin,
  `crawler_type` varchar(50) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  `file_path` text CHARACTER SET utf32 COLLATE utf32_bin,
  `crawled_at` datetime DEFAULT NULL,
  `json_data` longtext CHARACTER SET utf32 COLLATE utf32_bin,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM AUTO_INCREMENT=275 DEFAULT CHARSET=utf32 COLLATE=utf32_bin;

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `search_runs`
--

DROP TABLE IF EXISTS `search_runs`;
CREATE TABLE IF NOT EXISTS `search_runs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `query` varchar(255) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  `lang` varchar(10) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  `mode` varchar(50) CHARACTER SET utf32 COLLATE utf32_bin DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM AUTO_INCREMENT=9 DEFAULT CHARSET=utf32 COLLATE=utf32_bin;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
